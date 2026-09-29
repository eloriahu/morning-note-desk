# Original-source timing

The eligibility clock belongs to the specific development's **first public disclosure**, not to the article that led to its discovery. This applies to every market, category and edition. Afternoon originals must be strictly after 14:10 SGT on the run date and at or before the frozen run-start cutoff. Morning originals must pass the applicable morning market window.

## Trace the original

- Group syndicated articles, translations, wire copies and other reports of the same development. Follow attribution and hyperlinks to the originating report or company, exchange or regulator disclosure. Read the supporting text.
- Search the company and counterparties, relevant local-language names and the specific event **before the window as well as inside it**. Check prior saved editions. An in-window search alone cannot establish that the information is new.
- Prefer original official announcements for the disclosed facts and their release timestamps. Use the exchange's release/index timestamp if a PDF gives only a date; record where the timestamp was found and its timezone. The document's signature date, document properties, retrieval time and search-result date are not release-time evidence.
- For original media reporting, distinguish `Published` from `Updated`, trace wire credits and establish the first version carrying the fact. A later updated page qualifies only if an identifiable new development has a verifiable first-publication time. Do not assume a generic update time dates the new fact.
- Compare all reports of that same development. A later exchange/issuer copy does not supersede an earlier original report merely because it is official. An official confirmation can be a separate new development only if the changed status is material and explicitly distinguished from the earlier rumour/report.
- Record the original URL, publisher/type, precise native timestamp with timezone, the timestamp evidence, and what earlier sources were checked. The composer also stores the Singapore equivalent. Do not invent a timestamp when a source only gives a date, a relative time, conflicting times or an unconfirmed timezone. Hold the story while unresolved; do not substitute an in-window recap.

## New changes to old events

Use one independently timed development per story. A newly increased offer, approval, rejection, extension or material official confirmation may qualify on its own original release time. Describe exactly what changed in `origin.development`, retain the older event as explicitly identified background, and write the current update. If a story bundles separately timed developments, split it and check each origin. Rewording, repetition and a new URL are insufficient.

For example, in a 16:00 SGT afternoon run:

| First disclosure | Later coverage | Decision |
| --- | --- | --- |
| 13:55 today | Media reports at 14:45 and 15:30 | Exclude: original is before 14:10. |
| Previous Thursday | Monday article at 15:00 | Exclude: unchanged old news. |
| 14:20 today | Media report at 15:30 | May qualify, with the original read and cited. |
| Old deal, new offer-price increase first released 15:10 today | Coverage at 15:40 | May qualify for the price increase only. |
| Original time unknown | Article at 15:00 | Hold until the origin and its time are verified. |

## Research record and gate

Follow the required `origin` contract in [the draft schema](draft-schema.md). Original evidence must be read, cited and inside the window. Preserve other reports in `sources`; label only genuinely different earlier events as background and explain the distinction. The composer checks recorded times and inconsistencies, holds missing provenance, and exposes the chronology in the editor without cluttering the distribution email. It cannot independently prove that a researcher found the earliest report on the web or that two sources describe the same development; complete that source review before marking `origin.status` as `verified`.
