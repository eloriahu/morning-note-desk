"""Bounded public exchange headline discovery; linked filings need separate review."""
from datetime import datetime, timedelta
import json
import re
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

from lxml import html


def text(node):
    return ' '.join(' '.join(node.itertext()).split())


def fragment(value):
    return text(html.fragment_fromstring(str(value or ''), create_parent='div'))


def tree(raw):
    return html.fromstring(raw, parser=html.HTMLParser(encoding='utf-8'))


def stamp(value, fmt, zone):
    return datetime.strptime(value, fmt).replace(tzinfo=ZoneInfo(zone)).isoformat()


def lead(title, url, published, codes, name='', **extra):
    return dict(title=' '.join(codes + ([name] if name else []) + [title]),
                url=url, published=published, text='', exchange_tickers=codes, **extra)


def asx_items(raw, url):
    page = tree(raw)
    rows = page.xpath('//tr[td/a[contains(@href,"displayAnnouncement")]]')
    if not rows:
        raise ValueError('ASX announcement rows missing; check the page manually')
    out = []
    for row in rows:
        cells = row.xpath('./td')
        anchor = cells[3].xpath('./a')[0]
        out.append(lead((anchor.text or '').strip(), urljoin(url, anchor.get('href')),
                        stamp(text(cells[1]), '%d/%m/%Y %I:%M %p', 'Australia/Sydney'),
                        [text(cells[0]) + ' AU'],
                        price_sensitive=bool(cells[2].xpath('.//img[contains(@title,"price sensitive")]'))))
    return out


def nzx_items(raw, url):
    page = tree(raw)
    rows = page.xpath('//tr[contains(concat(" ",normalize-space(@class)," ")," announcement ")]')
    if not rows:
        raise ValueError('NZX announcement rows missing; check the page manually')
    out = []
    for row in rows:
        anchor = row.xpath('./td[@class="title"]/a')[0]
        value = text(row.xpath('./td[@class="date"]')[0])
        value = re.sub(r'\s+NZ(?:D|S)T$', '', value)
        out.append(lead(text(anchor), urljoin(url, anchor.get('href')),
                        stamp(value, '%d/%m/%Y %H:%M', 'Pacific/Auckland'),
                        [text(row.xpath('./td[@class="code"]')[0]) + ' NZ']))
    return out


def tdnet_items(raw, url, day):
    page = tree(raw)
    rows = page.xpath('//table[@id="main-list-table"]//tr[td[contains(@class,"kjTitle")]]')
    if not rows and not re.search('開示情報はありません|該当する情報はありません|に開示された情報はありません', text(page)):
        raise ValueError('TDnet announcement rows missing; check the day manually')
    out = []
    for row in rows:
        def cell(cls):
            return row.xpath('./td[contains(@class,"' + cls + '")]')[0]
        code = text(cell('kjCode'))
        codes = [code[:-1] + ' JP'] if re.fullmatch(r'[0-9A-Z]{4}0', code) else []
        anchor = cell('kjTitle').xpath('./a')[0]
        out.append(lead(text(anchor), urljoin(url, anchor.get('href')),
                        stamp(day + ' ' + text(cell('kjTime')), '%Y%m%d %H:%M', 'Asia/Tokyo'),
                        codes, text(cell('kjName')), exchange_security_code=code))
    # Follow only the public pagination filenames for this same date.
    pages = sorted(set(re.findall(r'I_list_\d{3}_' + day + r'\.html', raw.decode('utf-8'))))
    return out, [urljoin(url, p) for p in pages]


def hkex_items(raw, url):
    data = json.loads(raw)
    rows = json.loads(data['result']) if isinstance(data['result'], str) else data['result']
    out = []
    for row in rows:
        codes = [str(int(c)) + ' HK' for c in re.findall(r'\b\d{5}\b', fragment(row['STOCK_CODE']))]
        out.append(lead(fragment(row['TITLE']), urljoin(url, row['FILE_LINK']),
                        stamp(row['DATE_TIME'], '%d/%m/%Y %H:%M', 'Asia/Hong_Kong'),
                        codes, fragment(row['STOCK_NAME']),
                        announcement_category=fragment(row.get('LONG_TEXT'))))
    total = int(data['recordCnt'])
    if total and not out:
        raise ValueError('HKEX reported results but supplied no readable rows')
    return out, total


def days(start, end, zone):
    day = start.astimezone(ZoneInfo(zone)).date()
    last = end.astimezone(ZoneInfo(zone)).date()
    while day <= last:
        yield day.strftime('%Y%m%d')
        day += timedelta(days=1)


def collect_exchange(source, fetcher, start, asof, report):
    adapter = source['exchange_adapter']
    records = []
    report.update(discovery_only=True, pages_checked=[], day_coverage=[])
    if adapter in ('asx', 'nzx'):
        raw, _, url = fetcher.get(source['url'])
        records = (asx_items if adapter == 'asx' else nzx_items)(raw, url)
        report['pages_checked'].append(url)
        report['oldest_headline'] = min(r['published'] for r in records)
        if adapter == 'nzx' and min(datetime.fromisoformat(r['published']) for r in records) > start:
            report['truncated'] = True
            report['errors'].append('The current NZX list does not reach the window start; check the archive or issuer releases.')
        if adapter == 'asx':
            report['snapshot_dates'] = sorted({r['published'][:10] for r in records})
    elif adapter == 'tdnet':
        for day in days(start, asof, 'Asia/Tokyo'):
            pending = [urljoin(source['url'], 'I_list_001_' + day + '.html')]
            seen = set()
            before = len(records)
            errors_before = len(report['errors'])
            while pending and len(seen) < source.get('max_pages_per_day', 20):
                url = pending.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    raw, _, final_url = fetcher.get(url)
                    found, links = tdnet_items(raw, final_url, day)
                    records.extend(found)
                    report['pages_checked'].append(final_url)
                    pending.extend(p for p in links if p not in seen and p not in pending)
                except Exception as exc:
                    report['errors'].append(f'{day}: {type(exc).__name__}: {exc}')
            if pending:
                report['truncated'] = True
                report['errors'].append(f'{day}: TDnet pagination cap reached; additional pages need review.')
            report['day_coverage'].append(dict(day=day, headlines=len(records)-before,
                complete=not pending and len(report['errors']) == errors_before))
    elif adapter == 'hkex':
        for day in days(start, asof, 'Asia/Hong_Kong'):
            try:
                # Parameters from the public title-search page's load-more request.
                params = dict(sortDir=0, sortByOptions='DateTime', category=0, market='SEHK',
                              stockId=-1, documentType=-1, fromDate=day, toDate=day, title='',
                              searchType=0, t1code=-2, t2Gcode=-2, t2code=-2, rowRange=1000, lang='E')
                url = source['url'] + '?' + urlencode(params)
                raw, _, final_url = fetcher.get(url)
                found, total = hkex_items(raw, final_url)
                records.extend(found)
                report['pages_checked'].append(final_url)
                report['day_coverage'].append(dict(day=day, headlines=len(found), total=total, complete=len(found)>=total))
                if len(found) < total:
                    report['truncated'] = True
                    report['errors'].append(f'{day}: HKEX returned {len(found)} of {total}; remaining rows need review.')
            except Exception as exc:
                report['errors'].append(f'{day}: {type(exc).__name__}: {exc}')
                report['day_coverage'].append(dict(day=day, complete=False))
    else:
        raise ValueError('Unknown exchange adapter: ' + adapter)
    if not report['pages_checked']:
        raise ValueError('No exchange pages could be read: ' + '; '.join(report['errors']))
    # One filing can be listed against several securities; retain every code.
    unique = {}
    for record in records:
        if record['url'] in unique:
            previous = unique[record['url']]
            added = sorted(set(record['exchange_tickers']) - set(previous['exchange_tickers']))
            previous['exchange_tickers'] += added
            if added:
                previous['title'] = ' '.join(added) + ' ' + previous['title']
        else:
            unique[record['url']] = record
    return list(unique.values())
