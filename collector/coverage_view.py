"""A complete watchlist overview for the local review page, without network calls."""
from __future__ import annotations

from html import escape
from urllib.parse import urlsplit


def _text(value):
    return escape(str(value or ""), quote=True)


def _applies(source, ticker):
    """Respect both configured issuer restrictions and the run's actual scope."""
    if source.get("tickers") and ticker not in source["tickers"]:
        return False
    if "scope_tickers" in source and ticker not in source["scope_tickers"]:
        return False
    if source.get("scope_market") and not ticker.endswith(" " + source["scope_market"]):
        return False
    return True


def _checked(source, ticker):
    return (source.get("status") in ("ok", "partial")
            and ("successful_tickers" not in source or ticker in source["successful_tickers"]))


def _safe_link(url):
    """Only ordinary HTTP(S) links; no embedded credentials or executable schemes."""
    if not isinstance(url, str) or any(ord(char) < 32 for char in url):
        return ""
    try:
        parts = urlsplit(url.strip())
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username or parts.password or parts.port not in (None, 80, 443)):
            return ""
    except ValueError:
        return ""
    return url.strip()


def _status_label(source):
    labels = {"ok": "checked", "partial": "partly checked", "failed": "failed",
              "disabled": "disabled", "not_configured": "not configured",
              "not_applicable": "outside this run"}
    return labels.get(source.get("status"), "not checked")


def render_watchlist_overview(watchlist, records, coverage):
    """Render every tracked issuer, independently of how many stories the draft has.

    A direct source is explicitly marked issuer_official and bound to the ticker.
    General headlines, even when successfully checked, do not count as a company
    announcement connection. No-match results describe only the limited scan.
    """
    rows = []
    draft_companies = review_companies = direct_companies = 0
    for company in watchlist:
        ticker = str(company.get("ticker", ""))
        applicable = [source for source in coverage if _applies(source, ticker)]
        checked = [source for source in applicable if _checked(source, ticker)]
        direct = [source for source in applicable if source.get("issuer_official") is True
                  and ticker in source.get("tickers", [])]
        connected = [source for source in direct if _checked(source, ticker)]
        matched = [record for record in records if ticker in record.get("tickers", [])]
        ready = sum(bool(record.get("eligible")) for record in matched)
        held = len(matched) - ready
        draft_companies += bool(ready)
        review_companies += bool(held)
        direct_companies += bool(connected)

        if connected:
            direct_status = f"Connected ({len(connected)})"
            other_statuses = sorted({_status_label(source) for source in direct if source not in connected})
            if other_statuses:
                direct_status += "; others " + ", ".join(other_statuses)
        elif direct:
            direct_status = "Direct source " + ", ".join(sorted({_status_label(source) for source in direct}))
        else:
            direct_status = "Needs a direct source"

        if ready or held:
            counts = []
            if ready:
                counts.append(f"{ready} draft-ready candidate" + ("s" if ready != 1 else ""))
            if held:
                counts.append(f"{held} lead" + ("s" if held != 1 else "") + " to review")
            result = "; ".join(counts)
        elif not checked:
            result = "No sources checked for this company"
        elif not connected:
            result = "No matching items in limited general news"
        else:
            result = "No matching items in the limited sources checked"

        incomplete = sum(source.get("status") == "partial" for source in checked)
        checked_label = str(len(checked))
        if incomplete:
            checked_label += f" ({incomplete} partial)"
        source_links = []
        for source in applicable:
            url = _safe_link(source.get("url"))
            if not url:
                continue
            label = _text(source.get("name") or "Source")
            status = _text(_status_label(source))
            source_links.append(f'<a href="{_text(url)}" target="_blank" rel="noopener noreferrer">{label}</a> <span>({status})</span>')
        links = ('<details><summary>' + str(len(source_links)) + ' source links</summary>' + '<br>'.join(source_links) + '</details>') if source_links else 'No source links configured'
        rows.append(
            f'<tr data-ticker="{_text(ticker)}"><th scope="row">{_text(company.get("name") or ticker)}</th>'
            f'<td class="watchlist-ticker">{_text(ticker)}</td><td>{_text(direct_status)}</td>'
            f'<td>{_text(result)}</td><td>{_text(checked_label)}</td><td class="watchlist-links">{links}</td></tr>'
        )

    count = len(watchlist)
    count_label = f"{count} company tracked" if count == 1 else f"{count} companies tracked"
    empty = '<p class="watchlist-empty">No companies are configured. Add companies to the watchlist to begin.</p>' if not count else ""
    return (
        '<section class="watchlist-overview" id="watchlist-overview" aria-labelledby="watchlist-heading">'
        '<h2 id="watchlist-heading">Companies being tracked</h2>'
        f'<p class="watchlist-summary"><strong>{count_label}</strong> · '
        f'{draft_companies} with draft-ready candidates · {review_companies} with leads to review · '
        f'{direct_companies} with an official company source connected</p>'
        '<p>Every tracked company appears below. The email contains only candidates found in the selected time window. '
        'A limited scan with no matching items does not establish that a company has no news. '
        'Draft-ready candidates still need your review.</p>'
        + empty + '<div class="watchlist-table-wrap"><table class="watchlist-table">'
        '<thead><tr><th scope="col">Company</th><th scope="col">Ticker</th>'
        '<th scope="col">Official company source</th><th scope="col">This run</th>'
        '<th scope="col">Sources checked</th><th scope="col">Source links</th></tr></thead><tbody>'
        + "".join(rows) + '</tbody></table></div></section>'
    )
