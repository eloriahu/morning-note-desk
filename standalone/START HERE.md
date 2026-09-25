# Morning Note — shared prototype

Creates an editable Asia-Pacific email draft from configured public sources. It does not send emails.

**This is the broad-news collector with one demo priority name.** Discovery includes companies outside the list. Your private priority list remains in the original `morning-note` folder and is not included in this repository. For AI research and the finished email, use the separate Morning Note Desk workflow described in the repository handover; this standalone collector only prepares research inputs.

## Windows: first use

1. Download or clone the repository, then open its `standalone` folder. If you downloaded a ZIP from GitHub, extract it first.
2. Install **Python 3.11 or newer** if needed: https://www.python.org/downloads/
3. In the extracted folder, double-click **Setup first.cmd**. This creates a local `.venv` folder and downloads the packages listed in `requirements.txt` using pip.
4. When setup finishes, double-click **Run morning note.cmd**. The draft opens in your default browser.

For later runs, use **Run morning note.cmd**. You need internet access to the configured public sources. Normal public-source scans need no Codex, Claude, AI account, API key or email account. Some workplace computers restrict Python or package installation; follow your organization's software-installation process if that applies.

## Review and export

Click the email text to edit it. Use **Download edited .eml** or **Copy email** to keep your edits. Browser edits are not automatically saved. Each run creates an `output/` subfolder containing the review page, initial email draft, source evidence and collection report. Japanese-language items, restricted articles and items without verified publication times stay in a separate research review queue. Check the source and translate or resolve the missing evidence before using them in the email. Email clients vary in how they open `.eml` files; copying into a draft is an alternative.

## Included inputs

This share copy scans the public latest-news feeds or pages of **Nikkei, Yomiuri, Asahi, Mainichi, Sentaku, Diamond, RTHK finance, South China Morning Post business, ABC Australia business, Focus Taiwan and CADE**. It also checks **SoftBank's official press-release feed** as one demo priority name. Other companies can appear in the broad scan. Sentaku is a monthly publication, so an issue month alone cannot establish a recent publication time.

These are finite scans of the configured latest lists; they do not search each site's entire archive or provide full article coverage. Matching articles are checked where publicly readable. Edit `watchlist.json` for your own company names and Japanese aliases, and `config.json` for source settings. Adding a ticker alone does not establish complete company coverage. `inbox.json` starts empty and can accept manually supplied public document URLs.

No private example emails, screenshots, original research watchlist, prior drafts, history, credentials or email correspondence are included. This version has no connection to an internal publishing platform.

## Current limits

This is a working prototype, not a complete APAC research service. It generates source headlines and short excerpts for review. It does not yet provide full English summaries, translation, reliable fact-level novelty detection or deal calculations. A new document can repeat old facts. Body-only company mentions can be missed by headline discovery. Restricted content is not unlocked, and failed sources are reported. No matches in these limited sources does not establish that there is no news. There may be no eligible demo items on a given day.

The default window is 24 hours in the Asia/Singapore timezone. There is no installed scheduler. Normal runs read the configured public sources; setup downloads Python dependencies.

## Optional broader publisher search

Brave search is included but **off by default**. You do not need to buy anything to use the public-source scans. If your team confirms that it already has usable Brave Search API access, configure its key locally in the `BRAVE_SEARCH_API_KEY` environment variable and explicitly add `--with-search` to a command-line run. Do not put a key in the watchlist, source configuration, repository or a message.

Optional search submits bounded company-name queries to Brave, restricted to the six publisher domains. Its report identifies which names were searched and any query/result limits reached. Search snippets and search-engine dates are leads only; the original publisher's content and publication time still need verification. No search subscription is created, and the normal double-click launcher does not activate this option.

## Mac/Linux or command-line use

Python 3.11+ is required. From this folder:

```sh
python3 setup_environment.py
.venv/bin/python morning_note.py run --open
```

For Windows command-line use after setup:

```text
.venv\Scripts\python.exe morning_note.py run --ticker "9984 JP" --hours 12 --open
.venv\Scripts\python.exe morning_note.py run --topic "M&A" --hours 24 --open
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The Python code is portable; the `.cmd` launchers are Windows-only. Mac/Linux launch steps have not been tested in this Windows environment. Do not disable browser or operating-system security controls to run the package.

## Files and versions

`requirements.txt` lists third-party dependencies; those packages are downloaded at setup and are not bundled in this repository.
