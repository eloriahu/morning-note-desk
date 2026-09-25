# Running the workflow

Paths below are relative to the **plugin root**, two directories above `skills/morning-note`. Resolve that location from the skill file rather than assuming the plugin lives in the user's project.

Use the Python runtime available in the current Codex environment. If the workspace has a prepared `.venv`, prefer its Python (`.venv/Scripts/python.exe` on Windows or `.venv/bin/python` on macOS/Linux). The collector needs `lxml`, `pypdf` and timezone data; the email composer uses the Python standard library. If collection dependencies are unavailable, continue research through the available public web tools rather than claiming a scan ran.

## Gather inputs

From the current working workspace:

```text
python <plugin-root>/scripts/collect_news.py --workspace <workspace> --hours 24
```

The helper first looks for a compatible local `morning-note` project (or a current directory containing its `morning_note.py` and `config.json`). This preserves that project's configured priority list and sources. Otherwise it uses the bundled broad-source collector and an empty priority list in a new workspace run folder. Optional `--priority-file <path>` supplies a local JSON priority list to the bundled run. Optional `--as-of <ISO timestamp with offset>` sets a cutoff. No API credentials are required for the public-source scan.

Read the printed output directory's `evidence.json`, `headline-audit.json`, and collection report. Search tools in the current Codex task can supplement this raw material and perform priority-name checks. There is no need to obtain a Brave API key to do AI research in the task; the standalone collector's optional Brave connector remains disabled unless explicitly configured.

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
