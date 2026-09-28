# Morning Note Desk

This project helps prepare an Asia-Pacific morning research email. It scans a bounded set of public news feeds and latest-news pages, then uses a human or an AI assistant to investigate the leads, write sourced English updates, and produce an editable email draft. The draft is **never sent automatically**.

The repository contains the portable Morning Note Desk plugin and a sanitized Windows double-click prototype in `standalone/`. Its Python collector and email composer also run outside Codex. The Codex-specific instructions in `skills/morning-note/` describe the research workflow; they are not an AI model built into the Python scripts. Claude can use the same scripts after reading [CLAUDE_HANDOVER.md](CLAUDE_HANDOVER.md).

## Let a colleague test it

The repository is public, so a colleague can use **Code → Download ZIP** on GitHub, then extract it. For a simple Windows test, open [`standalone/`](standalone/), follow [`START HERE.md`](standalone/START%20HERE.md), and double-click **Setup first.cmd** followed by **Run morning note.cmd**. That prototype collects raw leads and excerpts; it does not perform the AI research or create the finished house-format draft.

To test the full Codex plugin, paste this repository link into **Codex Desktop on the colleague's own computer** and ask it to **install Morning Note Desk, set up its Python dependencies, run the tests, and verify the plugin is available**. [INSTALL_FOR_CODEX.md](INSTALL_FOR_CODEX.md) gives that Codex task the setup steps. If that task cannot download the repository, the colleague must use **Code → Download ZIP**, extract it, and open the folder in Codex Desktop before the task can continue. The desktop app may still require a restart or an Install click before the plugin appears. The bundled priority list is empty; give the colleague a separate local priority file if you want company-by-company checks. The plugin does not send mail. This plugin is not listed in the general public Plugins Directory.

## Quick start

Use Python 3.11 or newer. From this repository's root on **Windows PowerShell**:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r collector\requirements.txt
.\.venv\Scripts\python.exe scripts\collect_news.py --workspace .
```

On **macOS/Linux**:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r collector/requirements.txt
.venv/bin/python scripts/collect_news.py --workspace .
```

The source scan needs internet access. Its final output points to a run directory under `morning-note-runs/`; read that run's `headline-audit.json` and `evidence.json`, including its per-source coverage report. The scan's own preview is raw collection output, not a researched morning email. Commands below use `python` for brevity; use the matching virtual-environment Python shown above.

The launcher looks for a working `.venv` in the workspace or this plugin folder and checks `lxml`, `pypdf` and `tzdata` before starting a scan. If none is available, install `collector/requirements.txt` into the project's `.venv` and retry. A `--help` response is not a dependency or source-access check.

The included `collector/watchlist.json` is empty. To add *your own local* priority list for extra company checks, keep it outside the repository and run:

```sh
python scripts/collect_news.py --workspace . --priority-file path/to/your-priorities.json
```

The priority file is a JSON array of objects with `ticker`, `name`, optional `aliases`, and optional `category`. These names get extra attention; the broad news scan can discover other companies. Use `--as-of 2026-09-25T08:00:00+08:00` to set an explicit edition cutoff, or omit it to use the current time. The default window is 72 hours on Monday, covering Friday and weekend developments, and 24 hours on other days in Singapore time. An explicit `--hours` overrides that default. Compare prior editions to avoid repeating unchanged stories.

After researching the leads, write `research.json` according to [the research pack schema](skills/morning-note/references/draft-schema.md), then compose the email:

```sh
python scripts/compose_email.py --input path/to/research.json --output path/to/email-draft
```

The output contains `review.html`, `email.html`, `morning-note.txt`, an unsent `morning-note.eml`, and a validated copy of `research.json`. Open `review.html` to edit and copy the email or download an edited draft. A private house-style file can be supplied with `--style path/to/house-style.json`; no such file or reference email is included here.

## What is included

- `collector/`: broad public-source collection, provisional headline ranking, article extraction, review UI, and source configuration.
- `scripts/collect_news.py`: runs the bundled collector in a local workspace. It can use a compatible existing local project when present.
- `scripts/compose_email.py` and `scripts/email_layout.py`: validate a researched pack and produce the reference-style email and editable review page.
- `skills/morning-note/`: Codex research instructions, house-format specification, pack schema, and optional event/calendar research routing.
- `.codex-plugin/plugin.json`: Codex plugin manifest.
- `tests/`: portable helper and email layout tests.
- `standalone/`: allowlisted Windows prototype with setup/launch scripts, collector tests and one public demo priority name. Its raw excerpt email is separate from the plugin's AI-researched draft.

The current public collector config enables 16 discovery inputs: six Japanese publisher lists/feeds, four regional English news lists/feeds, one public competition-authority news page, and five exchange inputs covering ASX current/previous business day lists, NZX recent announcements, dated TDnet pages and HKEX English title search. Exchange headlines remain research leads until the linked filing is read, including those with low provisional keyword scores. Inspect source errors, snapshot dates, daily coverage and truncation flags. TDnet checks up to 20 pages per day; HKEX requests up to 1,000 rows per day. ASX/NZX snapshots and publisher lists have finite depth. Korea, India, Chinese-only HKEX filings, paid newswires and full issuer coverage remain gaps.

If collection returns `WinError 10013` or an explicit sandbox network denial, retry through the environment's approved network-capable execution path where available, or use public web research and report the outage. This error does not establish that a publisher requires a subscription. A zero-headline result after source failures is an incomplete scan.

## Development checks

```sh
python -m unittest discover -s tests -q
cd standalone && python -m unittest discover -s tests -q
```

The composer checks required fields, public-looking citation URLs, readable source status, and exact publication times inside the research window. It cannot prove that a claim is true, a ticker is correct, or a story is genuinely new. Those judgments belong in the research step and final review.

The repository includes no original sample emails, private 32-name priority list, contacts, logo, credentials, previous editions, scheduled task, email account, or external model API integration. The user's original double-click app remains a separate local project; `standalone/` is a sanitized prototype, not that private installation. Its demo watchlist is versioned for reproduction; replace it only in a private local copy, and never commit your actual priority names.
