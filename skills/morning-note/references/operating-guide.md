# Running the workflow

Paths below are relative to the **plugin root**, two directories above `skills/morning-note`. Resolve that location from the skill file rather than assuming the plugin lives in the user's project.

The collector needs `lxml`, `pypdf` and timezone data; the email composer uses the Python standard library. `scripts/collect_news.py` checks for these packages and uses a working `.venv` in the workspace or plugin root before trying its own Python. If no working runtime exists, create the plugin-root `.venv`, install `collector/requirements.txt` into it, and rerun collection. A failed collector run is not a broad scan; do not present an empty draft as a completed edition. If installation or source access is blocked, report the exact gap and continue public-web research only if it can produce a properly sourced draft.

## Gather inputs

From the current working workspace:

```text
python <plugin-root>/scripts/collect_news.py --workspace <workspace>
```

The helper first looks for a compatible local `morning-note` project (or a current directory containing its `morning_note.py` and `config.json`). This preserves that project's configured priority list and sources. Otherwise it uses the bundled broad-source collector and an empty priority list in a new workspace run folder. With no `--hours`, the collector selects morning or afternoon timing from the run time. See [market timing](market-windows.md) for normal cutoffs and holiday/short-session overrides. Morning runs use each market's latest completed desk close; Monday morning includes Friday evening and the weekend. Weekday afternoon runs cover only news from that day's close to the run cutoff. A market still open is pending; a market with no session that day has no afternoon window. Neither carries previous-session or weekend news forward. Auto mode treats 12:00 Singapore onward on weekdays as afternoon; `timing_edition` can explicitly select `morning` or `afternoon`. Verify holidays and shortened sessions. Explicit `--hours 12|24|48|72|96` selects a rolling window. Copy the reported `market_windows` into the research pack so composition enforces the same cutoffs. Optional `--priority-file <path>` supplies a local JSON priority list to the bundled run. Optional `--as-of <ISO timestamp with offset>` sets a cutoff. No API credentials are required for the public-source scan.

Read the printed output directory's `evidence.json`, `headline-audit.json`, and collection report. Search tools in the current Codex task can supplement this raw material and perform priority-name checks. There is no need to obtain a Brave API key to do AI research in the task; the standalone collector's optional Brave connector remains disabled unless explicitly configured.

If collection fails with `WinError 10013` or an explicit sandbox network denial, use the environment's approved network-capable execution path to retry the same public-source command. Do not disable security controls. If that path is unavailable, use the task's public web tools and record the outage.

The bundled collector now checks ASX current and previous business day announcement lists, the latest NZX list, dated TDnet pages with pagination, and HKEX English title search by date. These yield discovery metadata only. Read source documents before writing factual bullets. Inspect `day_coverage`, `snapshot_dates`, `truncated`, source errors and the full headline audit. ASX/NZX snapshots cannot guarantee historical or holiday coverage; HKEX has a 1,000-row daily cap and TDnet a 20-page daily cap. Missing pages and truncated dates require supplemental research.

If the headline audit is empty because sources failed, label it as a coverage outage and perform a separate public-web fallback scan. Also supplement incomplete markets with accessible EDINET, Bursa and KRX announcements, and publisher searches including Diamond. Record the actual lists, dates and failures. Inaccessible articles remain leads until a readable source supports the facts.

The collector's automatically assembled headline/excerpt email is **not the finished AI-researched email**. Produce a separate researched pack and pass it to the composer.

## Create the finished draft

Save the AI-authored pack at `<workspace>/morning-note-runs/<run>/research.json`, then run:

```text
python <plugin-root>/scripts/compose_email.py --input <research.json> --output <workspace>/morning-note-runs/<run>/email
```

Use [draft-schema.md](draft-schema.md) for exact fields and readiness checks, and [house-format.md](house-format.md) for the email layout. The email begins with a headline index and then NEWS SUMMARY; Top Stories are index pointers and all ready stories remain in their category details. Keep cutoff, AI/research labels, coverage gaps and held items in the editor view.

The composer automatically uses optional local branding at `<workspace>/morning-note/house-style.json`. To select a different local style, add `--style <house-style.json>` to the command. Relative `logo_path` values are resolved from that JSON file. Supplied title, subtitle, contact and footer wording are template text; no external requests or messages are triggered. Without local branding, use the generic layout. Private style files, logos, contacts, priority lists and reference messages are not bundled or copied into a sharing package.

Read the resulting email and review artifacts before delivering them. Confirm the compact ticker-first company headings, adjacent headline/source labels, `*` factual paragraphs and working internal index links. Keep prior runs rather than overwriting the user's edited draft. Do not add Recent Publications or Deal File links without current edition entries.

The plugin runs when invoked in Codex. A standalone double-click collector does not call Codex or perform AI reasoning. No scheduler, email sending or external model API has been provisioned. The plugin uses the capabilities available in the current Codex task; availability and source access remain visible limitations.
