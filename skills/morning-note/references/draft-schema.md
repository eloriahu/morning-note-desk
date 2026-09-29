# Research pack for the morning-note composer

Codex authors the research pack after reading and checking public sources. The local composer formats that pack into a reviewable email; it does not research, translate, check factual entailment or decide whether a development is materially new. Do not use a publisher excerpt as a substitute for the requested English synthesis.

Save UTF-8 JSON with these fields:

| Field | Meaning |
| --- | --- |
| `title` | Email subject; the masthead uses the local house title when configured. |
| `as_of` | Edition cutoff: full ISO timestamp with timezone, such as `2026-09-24T08:00:00+08:00`. |
| `window_start` | Earliest collection envelope, using the same full timestamp format. Inclusive for explicit rolling windows; per-market `start_inclusive` determines the actual boundary in market timing. |
| `timing_mode` | Use `market_close` for the default workflow, or `rolling_hours` for an explicit hours override. |
| `market_windows` | In market-close mode, copy the verified per-market map from collection: each market has `window_start`, `as_of`, `status` (`active` or `pending_start`), `edition`, `start_inclusive`, and session-date/basis notes. Preserve `expected_start` for a pending afternoon window. Afternoon starts are strictly exclusive; morning starts remain inclusive. Inactive entries are empty windows and cannot supply email stories. The top-level `window_start` is only the earliest collection envelope. See [market timing](market-windows.md). |
| `stories` | Array of researched story objects described below. Include held candidates as well as ready stories. |
| `coverage` | Array of short, honest strings describing sources checked, failures, access limits and scope. A failed search cannot establish that there was no news. |
| `priority_checks` | Optional JSON record of extra checks on the user's priority companies. These companies do not restrict broad discovery. |
| `upcoming_events` | Optional calendar-screening records described in [research-routing.md](research-routing.md). Displayed only in the editor; not processed as fresh news or copied into the distribution email. Record dates, time precision, current status and verification evidence honestly. |
| `top_stories` | Optional array of up to two ready story IDs highlighted in the opening headline index. These are pointers, not separate full stories. Every ready story, including Top Stories, remains in its normal category details below NEWS SUMMARY. |

Each story has:

| Field | Meaning |
| --- | --- |
| `id` | Unique nonempty string within this edition. |
| `company` | Researched company identity in English. If unresolved, leave empty and hold the story. |
| `tickers` | Array of verified ticker strings. An empty array is permitted when identity is established but a ticker has not been verified; never invent a ticker. |
| `market` | Primary market for timing, such as `JP`, `KR`, `AU` or `HK`. Required when ticker markets are unavailable or a primary listing needs to be selected. With several ticker markets and no explicit primary market, the latest starting point applies. Use `GLOBAL` only for regional macro context. |
| `category` | Exactly one of `Merger Arbitrage`, `Fundamental/Pre-Event`, `Relative Value`, `Other Strategy`. |
| `headline` | Short English headline supported by the cited evidence. |
| `bullets` | One or more objects with `text` (concise English synthesis) and `source_urls` (array of exact URLs present in this story's `sources`). Every bullet needs citations. |
| `sources` | Array of objects with `url`, `name`, `published_at`, `access`, and `date_precision`. Use the actual publication time; never substitute retrieval time, a search-result date or modified time for the article's publication. |
| `origin` | Required first-disclosure record for this specific development: `source_url`, `kind`, `status`, `development`, `timestamp_evidence`, and `verification_notes`, as specified below. Missing or unresolved provenance holds the story. |
| `novelty` | `new`, `changed`, `background`, or `unconfirmed`. Judge the actual information, not just a fresh page timestamp. |
| `review_status` | `ready` only after Codex's research checks; otherwise `hold`. Ready remains an editor-review draft, not a send instruction. |
| `review_notes` | Array of unresolved questions or useful editorial notes. Material unresolved claims require `hold`. |

Source `access` is `readable` only when the relevant public text was actually available and supports the claim. Use `restricted` for inaccessible or headline-only evidence; never infer an article's contents from a search snippet. Source `date_precision` is `time` for a confirmed full publication timestamp or `day` if only the date is known. Dates with only day precision stay held.

## Required original disclosure record

Apply [original-source timing](original-source-timing.md) before marking an origin verified. Each story represents one independently timed development.

| `origin` field | Required meaning |
| --- | --- |
| `source_url` | Exact URL of the original disclosure in this story's `sources`. A factual bullet must cite it. |
| `kind` | `exchange`, `issuer`, `regulator` or `original_reporting`. A later recap is not an original source. |
| `status` | `verified` only after reading the original and checking its chronology; otherwise `unconfirmed`. |
| `development` | The specific new fact or material change whose first disclosure is being timed. |
| `timestamp_evidence` | Where the original release time and timezone were verified, including the native timestamp/label and exchange index URL if needed. A generic page update date is insufficient. |
| `verification_notes` | Sources and earlier reporting actually checked, attribution chain and why this is the first disclosure of this development. Do not claim a check that was not performed. |

The original's native timestamp is its source object's `published_at`. The composer derives `original_published_at` and `original_published_at_sgt`; do not independently invent or maintain a second timestamp. It also records `applied_window_start`, `applied_start_inclusive` and the composition decision. These fields and the original-source audit appear in the review page/research pack, outside the distribution email.

Other sources default to `relationship: "same_development"`. Keep known earlier reports in the record. An earlier same-development timestamp holds the story until the actual origin is selected; an unconfirmed time holds the chronology for review. For an older, genuinely different event, explicitly set `relationship: "background"` and give `context_notes` explaining how it differs from the current development. Never relabel an earlier report of the same fact as background to pass the gate. Historical deal terms can be background to a newly announced price increase, for example.

## Draft eligibility

To publish a story into the draft, the composer requires a known company, a unique ID, a headline, a supported category, `review_status: "ready"`, `novelty: "new"` or `"changed"`, a verified `origin` record, and at least one nonempty cited bullet. **The original disclosure and every cited source** must be readable, have `date_precision: "time"`, and have a timezone-aware publication timestamp inside the applicable window. Afternoon uses `(14:10 SGT, as_of]`; morning/explicit rolling windows use an inclusive start unless specified otherwise. All citation URLs must match that story's source list. Unsafe URLs, duplicate source URLs, restricted sources, old/future evidence, missing citation metadata and missing origin verification hold the entire story. An older document can remain as explicitly labelled uncited background; if a bullet depends on it, split the current update from historical context or hold the unsupported update. A later media or exchange publication cannot make an older original eligible.

Structural validation does not prove that the earliest disclosure has actually been found, that English wording is accurate, that a source supports a bullet, that a company/ticker mapping is right, or that a story is new. Codex must complete those checks before marking a story ready. The user reviews the resulting email.

In `market_close` mode, the original disclosure and every cited publication must fall inside the story's applicable market window, not merely the overall envelope. Missing market/window mappings hold the story. Older packs without market timing retain their explicit global window, but their stories now stay held until original-disclosure evidence is supplied. Do not auto-populate verified origin metadata from the first listed or newest source. Existing saved drafts are not rewritten.

This deliberately incomplete example demonstrates a **held workflow item**, not a financial claim or a real news event:

```json
{
  "title": "Asia-Pacific Morning Note — example format",
  "as_of": "2026-09-24T08:00:00+08:00",
  "window_start": "2026-09-23T08:00:00+08:00",
  "stories": [
    {
      "id": "format-example-only",
      "company": "",
      "tickers": [],
      "category": "Other Strategy",
      "headline": "Formatting example awaiting research",
      "bullets": [],
      "sources": [],
      "novelty": "unconfirmed",
      "review_status": "hold",
      "review_notes": ["Replace this example with evidence from the actual edition."]
    }
  ],
  "coverage": ["Formatting example only; no source research has been performed."],
  "priority_checks": [],
  "top_stories": []
}
```

Run the plugin's `scripts/compose_email.py` with `--input <research.json> --output <edition-directory>` using Python 3.11 or later. Optional `--style <house-style.json>` selects a local style explicitly; otherwise the workspace's `morning-note/house-style.json` is discovered when available. Relative logo paths resolve against the style file's directory. No branding, contact lines or private images are bundled with the plugin. It uses only the standard library and performs no network requests. The output directory receives `email.html`, `morning-note.txt`, `morning-note.eml`, `review.html`, and `research.json`. Existing files with those names are replaced. The saved pack preserves all stories and adds `composition_status` and `composition_reasons` per story plus a composition summary.

The email layout is an opening headline index, then **NEWS SUMMARY** with category sections containing every ready story. Follow [house-format.md](house-format.md) for typography and order. Cutoff/window, AI/research wording, coverage, priority-check diagnostics and held items are editor-only metadata. They stay in the review page and research record rather than the copyable distribution email.

Open `review.html` to edit the draft, copy it, or download an edited `.eml`. The `.eml` has `X-Unsent: 1` and no sender, recipient, CC or BCC. It is never sent automatically. Review-page edits are saved only through copy/download; they do not change the research pack. Held items stay outside the email and must be corrected in the research pack before composing again.
