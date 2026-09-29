"""Morning market-close windows and a strict daily 14:10 Singapore afternoon floor.

These are desk news cutoffs, not an authoritative exchange holiday calendar.
AU deliberately preserves the requested fixed 14:15 Singapore desk cutoff.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


DEFAULT_CLOSES = {
    'JP': {'timezone': 'Asia/Tokyo', 'close': '15:30'},
    'KR': {'timezone': 'Asia/Seoul', 'close': '15:30'},
    'AU': {'timezone': 'Asia/Singapore', 'close': '14:15', 'basis': 'fixed SGT desk cutoff'},
    'HK': {'timezone': 'Asia/Hong_Kong', 'close': '16:10'},
    'CH': {'timezone': 'Asia/Shanghai', 'close': '15:00'},
    'TT': {'timezone': 'Asia/Taipei', 'close': '13:30'},
    'NZ': {'timezone': 'Pacific/Auckland', 'close': '17:00:30'},
    'SP': {'timezone': 'Asia/Singapore', 'close': '17:16'},
    'IN': {'timezone': 'Asia/Kolkata', 'close': '15:30'},
    'MK': {'timezone': 'Asia/Kuala_Lumpur', 'close': '17:00'},
    'IJ': {'timezone': 'Asia/Jakarta', 'close': '16:15'},
    'TB': {'timezone': 'Asia/Bangkok', 'close': '16:40'},
    'PM': {'timezone': 'Asia/Manila', 'close': '15:15'},
    'VN': {'timezone': 'Asia/Ho_Chi_Minh', 'close': '15:00'},
}
ALIASES = {'CN': 'CH', 'TW': 'TT', 'SG': 'SP', 'MY': 'MK', 'KS': 'KR', 'KQ': 'KR',
           'ID': 'IJ', 'TH': 'TB', 'PH': 'PM'}


def market_code(value):
    code = str(value or '').strip().upper()
    return ALIASES.get(code, code)


def ticker_market(value):
    """Read the market suffix of a verified ticker, including Bloomberg Equity IDs."""
    parts = value.split() if isinstance(value, str) else []
    if parts and parts[-1].upper() == 'EQUITY':
        parts.pop()
    return market_code(parts[-1]) if len(parts) >= 2 else ''


def latest_close(asof, rule):
    zone = ZoneInfo(rule['timezone'])
    local = asof.astimezone(zone)
    overrides = rule.get('sessions', {})  # ISO date -> HH:MM, or null for a holiday.
    for offset in range(370):
        day = local.date() - timedelta(days=offset)
        key = day.isoformat()
        if key in overrides:
            close = overrides[key]
        else:
            close = rule['close'] if day.weekday() < 5 else None
        if close is None:
            continue
        cutoff = datetime.combine(day, time.fromisoformat(close), zone)
        if cutoff <= asof:
            return cutoff, key, 'session override' if key in overrides else rule.get('basis', 'normal weekday close')
    raise ValueError('No completed market session within 370 days')


def edition_for(config, asof):
    """Afternoons use the fixed Singapore window every day; mornings span overnight."""
    edition = config.get('timing_edition', 'auto')
    if edition not in ('auto', 'morning', 'afternoon'):
        raise ValueError('timing_edition must be auto, morning or afternoon')
    if edition == 'auto':
        local = asof.astimezone(ZoneInfo('Asia/Singapore'))
        boundary = time.fromisoformat(config.get('afternoon_start', '12:00'))
        edition = 'afternoon' if local.time() >= boundary else 'morning'
    return edition


def build_windows(config, asof):
    if asof.tzinfo is None:
        raise ValueError('The edition cutoff requires a timezone')
    mode = config.get('timing_mode', 'rolling_hours')
    if mode == 'rolling_hours':
        return {}, asof - timedelta(hours=config.get('lookback_hours', 24))
    if mode != 'market_close':
        raise ValueError('timing_mode must be market_close or rolling_hours')
    rules = {m: dict(rule) for m, rule in DEFAULT_CLOSES.items()}
    for m, rule in config.get('market_close_rules', {}).items():
        code = market_code(m)
        rules[code] = dict(rules.get(code, {}), **rule)
    output = {}
    display_zone = ZoneInfo(config.get('timezone', 'Asia/Singapore'))
    edition = edition_for(config, asof)
    if edition == 'afternoon':
        singapore = ZoneInfo('Asia/Singapore')
        day = asof.astimezone(singapore).date()
        cutoff = datetime.combine(day, time(14, 10), singapore)
        status = 'active' if asof > cutoff else 'pending_start'
        start = min(cutoff, asof)
        window = dict(window_start=start.astimezone(display_zone).isoformat(),
                      as_of=asof.isoformat(), session_date=day.isoformat(),
                      status=status, edition=edition, start_inclusive=False,
                      expected_start=cutoff.isoformat(),
                      basis='Strictly after 14:10 Singapore on the edition date, for every market',
                      calendar_status='Fixed afternoon clock window; exchange sessions do not change it.')
        return {market: dict(window) for market in (*rules, 'GLOBAL')}, start
    for market, rule in rules.items():
        cutoff, day, basis = latest_close(asof, rule)
        output[market] = dict(window_start=cutoff.astimezone(display_zone).isoformat(),
                              as_of=asof.isoformat(), session_date=day, basis=basis,
                              status='active', edition=edition, start_inclusive=True,
                              calendar_status='Normal weekdays plus configured session overrides; verify exchange holidays and special sessions.')
    earliest = min(datetime.fromisoformat(w['window_start']) for w in output.values())
    output['GLOBAL'] = dict(window_start=earliest.isoformat(), as_of=asof.isoformat(),
                            status='active', edition=edition, start_inclusive=True,
                            basis='Regional macro context: earliest of the morning market windows')
    return output, earliest


def infer_markets(record, source, matched_tickers=()):
    explicit = record.get('market')
    if explicit:
        return [market_code(explicit)]
    tickers = record.get('exchange_tickers') or record.get('tickers') or list(matched_tickers) or source.get('tickers', [])
    markets = sorted({ticker_market(t) for t in tickers if ticker_market(t)})
    if markets:
        return markets
    # A publisher's country does not establish the listing of an unknown issuer.
    if source.get('kind') == 'exchange_index' or source.get('issuer_official'):
        hint = source.get('scope_market') or source.get('timing_market')
        return [market_code(hint)] if hint else []
    return []


def record_window(record, source, fallback, matched_tickers=()):
    windows = source.get('market_windows', {})
    markets = infer_markets(record, source, matched_tickers)
    if not windows:
        return fallback, markets, True
    valid = bool(markets) and all(m in windows for m in markets)
    if valid:
        # Multi-market candidates must meet each cutoff until research selects a primary market.
        active = all(windows[m].get('status', 'active') == 'active' for m in markets)
        return max(datetime.fromisoformat(windows[m]['window_start']) for m in markets), markets, active
    return fallback, markets, False


def start_inclusive(source, markets):
    windows = source.get('market_windows', {})
    return all(windows.get(m, {}).get('start_inclusive', True) for m in (markets or ['GLOBAL']))
