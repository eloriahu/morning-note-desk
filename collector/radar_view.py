"""Render broad news discovery and its audit trail without making network calls.

The priority list determines extra checks, not which market candidates are shown.
All content received from publishers, including links, is treated as data.
"""
from __future__ import annotations

from html import escape
import math
from urllib.parse import urlsplit


def _text(value):
    return escape(str(value if value is not None else ""), quote=True)


def _values(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None and str(item)]
    return [str(value)] if str(value) else []


def _count(value):
    try:
        return max(0, int(value))
    except (ValueError, TypeError, OverflowError):
        return 0


def _score(record):
    try:
        score = float(record.get("attention_score", 0))
        return score if math.isfinite(score) else 0
    except (ValueError, TypeError, OverflowError):
        return 0


def _role(item):
    # Legacy general-news entries have no role; official issuer entries are extra
    # company checks. An explicit role always wins.
    return item.get("collection_role") or ("priority" if item.get("issuer_official") else "market")


def _safe_url(value):
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return ""
    value = value.strip()
    try:
        parts = urlsplit(value)
        if (parts.scheme.lower() not in ("http", "https") or not parts.hostname
                or parts.username or parts.password or parts.port not in (None, 80, 443)):
            return ""
    except ValueError:
        return ""
    return value


def _link(value, label):
    url = _safe_url(value)
    return (f'<a href="{_text(url)}" target="_blank" rel="noopener noreferrer">{_text(label)}</a>'
            if url else _text(label))


def _source_name(item):
    source = item.get("source") or item.get("name") or item.get("source_id") or "Source unconfirmed"
    if isinstance(source, dict):
        return source.get("name") or source.get("id") or "Source unconfirmed"
    return source


def _date(item):
    date = item.get("published") or item.get("published_at")
    precision = item.get("date_precision")
    if not date:
        return "Publication time unconfirmed"
    if precision in ("day", "date"):
        return f"{date} (date only; time unconfirmed)"
    if precision in ("month", "year", "missing", "unknown"):
        return f"{date} (publication time unconfirmed)"
    return str(date)


def _candidate_status(record):
    if not record.get("tickers"):
        return "Company/ticker review required"
    return "Draft candidate — review required" if record.get("eligible") else "Held for review"


def _review_notes(record):
    notes = []
    access = record.get("access_status")
    if access in ("restricted", "metadata_only", "unavailable"):
        notes.append({"restricted": "Restricted article — public headline or metadata only.",
                      "metadata_only": "Public headline or metadata only; article text unverified.",
                      "unavailable": "Article unavailable; its contents remain unverified."}[access])
    language = str(record.get("language") or "").lower()
    if language and not language.startswith("en"):
        label = {"ja": "Japanese", "jp": "Japanese", "zh": "Chinese", "ko": "Korean",
                 "pt": "Portuguese"}.get(language, language)
        notes.append(f"Original language: {label} — English summary needed.")
    if not record.get("published") or record.get("date_precision") in ("day", "date", "month", "year", "missing", "unknown"):
        notes.append("Publication time needs checking before inclusion in this edition.")
    for flag in _values(record.get("flags")):
        if flag not in notes:
            notes.append(flag)
    return notes


def _source_status(source):
    return {"ok": "Scan finished within stated limits", "partial": "Partial scan",
            "failed": "Scan failed", "disabled": "Disabled", "not_configured": "Not configured",
            "not_applicable": "Outside this run"}.get(source.get("status"), "Not checked")


def _coverage_table(sources, heading, table_id):
    rows = []
    for source in sources:
        notes = _values(source.get("coverage_note"))
        errors = source.get("errors") or []
        for error in errors if isinstance(errors, list) else [errors]:
            if isinstance(error, dict):
                notes.append(str(error.get("message") or error.get("error") or error.get("status") or "Source error"))
            else:
                notes.append(str(error))
        rows.append(
            f'<tr data-source-id="{_text(source.get("id", ""))}">'
            f'<th scope="row">{_link(source.get("url"), _source_name(source))}</th>'
            f'<td>{_text(_source_status(source))}</td>'
            f'<td>{_count(source.get("discovered"))}</td>'
            f'<td>{_count(source.get("articles_attempted"))}</td>'
            f'<td>{_text(" ".join(notes))}</td></tr>'
        )
    if not rows:
        return f'<h3>{_text(heading)}</h3><p>No sources configured for this part of the run.</p>'
    return (f'<h3>{_text(heading)}</h3><div class="watchlist-table-wrap"><table class="watchlist-table radar-source-table" id="{table_id}">'
            '<thead><tr><th scope="col">Source</th><th scope="col">Scan state</th>'
            '<th scope="col">Items returned</th><th scope="col">Article checks attempted</th>'
            '<th scope="col">Coverage limits</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table></div>')


def _audit_state(item):
    stage = str(item.get("stage") or item.get("state") or "logged")
    labels = {"candidate": "Candidate retained", "selected": "Candidate retained", "retained": "Candidate retained",
              "old": "Outside time window", "future": "Future timestamp — held", "undated": "Date unconfirmed",
              "no_signal": "No event signal detected", "unmatched": "No event signal detected",
              "duplicate": "Duplicate", "unchanged": "Already seen", "article_limit": "Article check limit reached",
              "fetch_failed": "Article check failed", "logged": "Headline recorded"}
    return labels.get(stage, stage.replace("_", " "))


def render_market_radar(records, coverage, discovery_log, priority_count):
    """Render every market candidate plus a complete, collapsed headline audit.

    Counts of returned items come from source reports, while the audit count is
    the number of supplied log entries. They need not agree: sources can report
    old items or failures that never become candidates. Neither implies complete
    market coverage or verifies that a named company is listed.
    """
    market_records = sorted((record for record in records if _role(record) == "market"), key=lambda r: -_score(r))
    market_sources = [source for source in coverage if _role(source) == "market"]
    priority_sources = [source for source in coverage if _role(source) == "priority"]
    market_log = [item for item in discovery_log if _role(item) == "market"]
    outsiders = sum(not record.get("tickers") for record in market_records)
    headlines = sum(_count(source.get("discovered")) for source in market_sources)
    attempted = sum(_count(source.get("articles_attempted")) for source in market_sources)
    checked = sum(source.get("status") in ("ok", "partial") for source in market_sources)
    failed = sum(source.get("status") == "failed" for source in market_sources)
    partial = sum(source.get("status") == "partial" for source in market_sources)
    pieces = [
        '<section class="market-radar watchlist-overview" id="market-radar" aria-labelledby="market-radar-heading">',
        '<h2 id="market-radar-heading">Market-wide news radar</h2>',
        f'<p class="radar-workflow"><strong>Market news → new candidates → deeper priority checks</strong><br>'
        f'The {_count(priority_count)} priority companies receive extra checks. '
        'The market scan can surface names outside that list.</p>',
        f'<p class="watchlist-summary"><strong>{headlines} headline items returned</strong> · '
        f'{attempted} article checks attempted · {len(market_records)} market candidates · '
        f'{outsiders} outside the priority list</p>',
        f'<p>{checked} market source scans returned results; {partial} are partial and {failed} failed. '
        'Counts describe this limited run, not all news published. Returned headlines may include old or undated items.</p>',
        '<h3>Candidates to review</h3>',
        '<p>Attention scores are provisional rules based on detected events. '
        'They help order the review queue; they do not verify facts, company identity or investment merit.</p>',
    ]
    if not market_records:
        if not checked:
            pieces.append('<p class="radar-empty warning">No market candidates are available because no market source scan returned usable results. Coverage is incomplete.</p>')
        else:
            pieces.append('<p class="radar-empty">No market candidates were retained from these limited scans. This does not establish that there is no market news.</p>')
    for rank, record in enumerate(market_records, 1):
        tickers = _values(record.get("tickers"))
        badge = ("Priority-list match: " + ", ".join(tickers) if tickers else
                 "Outside priority list — company/ticker review needed")
        reasons = _values(record.get("attention_reasons"))
        notes = _review_notes(record)
        score = _score(record)
        score_text = f"{score:g}"
        title = record.get("title") or record.get("discovery_title") or "Untitled source item"
        pieces.extend([
            f'<article class="lead-card radar-candidate" data-candidate-id="{_text(record.get("id", ""))}" data-priority-match="{"true" if tickers else "false"}">',
            f'<span class="pill">{_text(badge)}</span>',
            f'<h3>{rank}. {_text(title)}</h3>',
            f'<p>{_text(_source_name(record))} · {_text(_date(record))}</p>',
            f'<p><strong>{_text(_candidate_status(record))}</strong> · Attention score: {score_text}</p>',
            f'<p>Why surfaced: {_text("; ".join(reasons) if reasons else "Reason not supplied; inspect the source.")}</p>',
        ])
        if notes:
            pieces.append('<ul>' + ''.join(f'<li>{_text(note)}</li>' for note in notes) + '</ul>')
        if _safe_url(record.get("url")):
            pieces.append('<p>' + _link(record["url"], "Read public source") + '</p>')
        else:
            pieces.append('<p class="warning">No usable public source link supplied.</p>')
        pieces.append('</article>')
    pieces.append('<details class="radar-coverage"><summary>Source coverage and extra priority checks</summary>')
    pieces.append(_coverage_table(market_sources, "Market news scans", "radar-market-sources"))
    pieces.append(_coverage_table(priority_sources, "Extra company checks for the priority list", "radar-priority-sources"))
    pieces.append('</details>')
    pieces.append(f'<details class="radar-headline-audit"><summary>Headline audit — {len(market_log)} logged market items</summary>')
    pieces.append('<p>All supplied market headline log entries appear here, including discarded or undated items. '
                  'A logged headline is not a verified story or a fresh publication.</p>')
    if not market_log:
        pieces.append('<p>No headline audit entries were recorded for this run.</p>')
    else:
        pieces.append('<div class="watchlist-table-wrap"><table class="watchlist-table" id="radar-audit-table">'
                      '<thead><tr><th scope="col">Headline</th><th scope="col">Source</th>'
                      '<th scope="col">Publication time</th><th scope="col">Reason</th><th scope="col">State</th></tr></thead><tbody>')
        for item in market_log:
            reasons = _values(item.get("reason") or item.get("attention_reasons") or item.get("flags"))
            pieces.append('<tr>'
                          f'<th scope="row">{_link(item.get("url"), item.get("title") or item.get("discovery_title") or "Untitled source item")}</th>'
                          f'<td>{_text(_source_name(item))}</td><td>{_text(_date(item))}</td>'
                          f'<td>{_text("; ".join(reasons))}</td><td>{_text(_audit_state(item))}</td></tr>')
        pieces.append('</tbody></table></div>')
    pieces.append('</details></section>')
    return "".join(pieces)
