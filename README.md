# Morning Note Desk

This project helps prepare an Asia-Pacific morning research email. It scans a bounded set of public news feeds and latest-news pages, then uses a human or an AI assistant to investigate the leads, write sourced English updates, and produce an editable email draft. The draft is **never sent automatically**.

The repository is the portable Morning Note Desk plugin. Its Python collector and email composer also run outside Codex. The Codex-specific instructions in `skills/morning-note/` describe the research workflow; they are not an AI model built into the Python scripts. Claude can use the same scripts after reading [CLAUDE_HANDOVER.md](CLAUDE_HANDOVER.md).

## Quick start

Use Python 3.11 or newer. From this repository's root on **Windows PowerShell**:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r collector\requirements.txt
.\.venv\Scripts\python.exe scripts\collect_news.py --workspace . --hours 24
```

On **macOS/Linux**:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r collector/requirements.txt
.venv/bin/python scripts/collect_news.py --workspace . --hours 24
```

The source scan needs internet access. Its final output points to a run directory under `morning-note-runs/`; read that run's `headline-audit.json` and `evidence.json`, including its per-source coverage report. The scan's own preview is raw collection output, not a researched morning email. Commands below use `python` for brevity; use the matching virtual-environment Python shown above.

The included `collector/watchlist.json` is empty. To add *your own local* priority list for extra company checks, keep it outside the repository and run:

```sh
python scripts/collect_news.py --workspace . --hours 24 --priority-file path/to/your-priorities.json
```

The priority file is a JSON array of objects with `ticker`, `name`, optional `aliases`, and optional `category`. These names get extra attention; the broad news scan can discover other companies. Use `--as-of 2026-09-25T08:00:00+08:00` to set an explicit edition cutoff, or omit it to use the current time.

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

The current public collector config enables 11 sources: six Japanese publisher lists/feeds, four regional English news lists/feeds, and one public competition-authority news page. These are bounded recent listings, not complete site archives. Article access varies; some leads remain restricted, undated, or unavailable. Korea, India, many exchange announcements, paid newswires, and full issuer coverage remain gaps. Source availability and terms should be checked before expanding collection.

## Development checks

```sh
python -m unittest discover -s tests -q
```

The composer checks required fields, public-looking citation URLs, readable source status, and exact publication times inside the research window. It cannot prove that a claim is true, a ticker is correct, or a story is genuinely new. Those judgments belong in the research step and final review.

The repository includes no original sample emails, private 32-name priority list, contacts, logo, credentials, previous editions, scheduled task, email account, or external model API integration. The user's original double-click app remains a separate local project; this repository includes its portable collector helper, not that private installation.
