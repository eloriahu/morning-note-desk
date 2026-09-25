# Research pack for the morning-note composer

Codex authors the research pack after reading and checking public sources. The local composer formats that pack into a reviewable email; it does not research, translate, check factual entailment or decide whether a development is materially new. Do not use a publisher excerpt as a substitute for the requested English synthesis.

Save UTF-8 JSON with these fields:

| Field | Meaning |
| --- | --- |
| `title` | Email subject; the masthead uses the local house title when configured. |
| `as_of` | Edition cutoff: full ISO timestamp with timezone, such as `2026-09-24T08:00:00+08:00`. |
| `window_start` | Inclusive start of the research window, using the same full timestamp format. |
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
| `category` | Exactly one of `Merger Arbitrage`, `Fundamental/Pre-Event`, `Relative Value`, `Other Strategy`. |
| `headline` | Short English headline supported by the cited evidence. |
| `bullets` | One or more objects with `text` (concise English synthesis) and `source_urls` (array of exact URLs present in this story's `sources`). Every bullet needs citations. |
| `sources` | Array of objects with `url`, `name`, `published_at`, `access`, and `date_precision`. Use the actual publication time; never substitute retrieval time, a search-result date or modified time for the article's publication. |
| `novelty` | `new`, `changed`, `background`, or `unconfirmed`. Judge the actual information, not just a fresh page timestamp. |
| `review_status` | `ready` only after Codex's research checks; otherwise `hold`. Ready remains an editor-review draft, not a send instruction. |
| `review_notes` | Array of unresolved questions or useful editorial notes. Material unresolved claims require `hold`. |

Source `access` is `readable` only when the relevant public text was actually available and supports the claim. Use `restricted` for inaccessible or headline-only evidence; never infer an article's contents from a search snippet. Source `date_precision` is `time` for a confirmed full publication timestamp or `day` if only the date is known. Dates with only day precision stay held. Additional fields may be retained for provenance, but do not alter the gates.

To publish a story into the draft, the composer requires a known company, a unique ID, a headline, a supported category, `review_status: "ready"`, `novelty: "new"` or `"changed"`, and at least one nonempty cited bullet. **Every cited source** must be readable, have `date_precision: "time"`, and have a timezone-aware publication timestamp within `[window_start, as_of]`. All citation URLs must match that story's source list. Unsafe URLs, duplicate source URLs, restricted sources, old/future evidence and missing citation metadata hold the entire story. An older document can remain as uncited context in `sources`; if a bullet depends on it, split the current update from historical context or hold the unsupported update.

Structural validation does not prove that English wording is accurate, that a source supports a bullet, that a company/ticker mapping is right, or that a story is new. Codex must complete those checks before marking a story ready. The user reviews the resulting email.

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
