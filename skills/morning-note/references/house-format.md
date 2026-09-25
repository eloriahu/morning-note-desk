# House email format

Use a compact research email, matching a supplied reference template when present. This document is a generic layout specification: it contains no private branding, company names, contacts or reference-message content.

## Reading order

1. Optional local logo at its configured width, followed by a thin grey rule.
2. A two-column header: note title on the left; supplied subtitle and contact text on the right.
3. Region label and the opening headline index. Show up to two Top Stories as ticker/headline links, followed by the nonempty category indexes.
4. **NEWS SUMMARY**.
5. Full story details under Merger Arbitrage, Fundamental/Pre-Event, Relative Value and Other Strategy, in that order. Every ready story appears once in its normal category details, including any highlighted as a Top Story.
6. Optional supplied local footer. Recent Publications or Deal File links appear only when the current edition supplies entries; do not reuse historical links to fill space.

Top Stories are navigation pointers in the index, not a second full-story section. Category index entries also point to the corresponding detailed story.

## Compact story treatment

Use Arial, generally 10 pt, with restrained spacing, black body text, dark-blue headings/links and thin grey dividing rules. Lead with the verified ticker followed by the uppercase English company name. Put the concise headline on the following line, with its source label beside it. Render one to three original factual paragraphs beginning with a literal `*`, preserving supporting links and attribution. Do not invent tickers or shorten names in ways that change the issuer identity.

Generic skeleton:

```text
[Optional local logo]
NOTE TITLE                                      SUPPLIED SUBTITLE
                                                SUPPLIED CONTACT

REGION
Top Stories
TICKER    Headline linked to the detailed story

Merger Arbitrage
TICKER    Headline linked to the detailed story

NEWS SUMMARY
Merger Arbitrage                                 Back to Top
TICKER    COMPANY NAME
Concise new-fact headline                        Source
* Attributed new fact supported by the source.
* Distinct additional fact, if useful and supported.

[Optional supplied contact/footer text]
```

## Email versus editor view

The copyable distribution email contains the note, index, sourced stories and optional supplied footer. Cutoff/window details, AI/research labels, coverage gaps, priority-check diagnostics, readiness gates and held-item explanations belong in the editor review and research JSON. Keep those controls outside the editable/copyable email container.

## Optional private branding

The composer discovers `<workspace>/morning-note/house-style.json`, or accepts `--style <path>`. Relative `logo_path` resolves against the style file. Supported template values include `name`, `title`, `region`, `subtitle`, `contact_email`, `logo_path`, `logo_width` and optional `footer` text/groups. Reproduce supplied text; do not invent new contacts or licensing claims.

Keep local style files, logo assets, reference messages and contact information outside the plugin and all sharing bundles. Only this generic specification and formatter belong in the portable plugin.
