# Event research and upcoming dates

The morning-note workflow owns the email. Use installed event skills as focused research support: they supply search plans, evidence standards and analytical checks, not additional news feeds, subscriptions, complete market databases or background services. Preserve broad discovery beyond the priority list, followed by extra checks on the user's priority names. Public websites and company announcements remain the default source scope.

## Choose the smallest useful route

| Research need | Installed capability | Contribution to the morning note |
| --- | --- | --- |
| Discover newly announced APAC deals and amendments | `apac-equity-desk:deal-radar` | Search the actual exchange, regulator and issuer source universe; distinguish preliminary proposals, firm offers and amendments; group duplicate reports. |
| Screen broader corporate events | `event-driven-desk:event-desk` → `special-situations`, or the APAC `special-situations` sibling | Identify a discrete event, affected security, eligibility, timing and useful next check across tenders, spins, activism, rights, capital returns and other situations. A headline score is not an investment conclusion. |
| Refresh priority names and previously discovered deals | `event-driven-desk:deal-monitor`, or the APAC `deal-monitor` sibling | Compare dated prior research with current terms, approvals, votes, court steps, financing, deadlines and status. Preserve old snapshots; repeated terms do not become new news. |
| Screen upcoming catalysts | `apac-equity-desk:event-radar`; use Public Equity Investing's `catalyst-calendar` for a more detailed event register | Verify upcoming dates, timezone, timing confidence, status and relevance from company, exchange, regulator, court, central-bank or statistical-agency sources. |
| Resolve a consequential event after finding a lead | Public Equity Investing's `event-driven-analyzer`, through its `public-equity-investing` router | Check event mechanics, controlling documents, conditions, timing and competing outcomes. Use payoff/probability math only when needed and supported by timestamped inputs. Do not run a full investment report for every headline. |

These routes are optional capabilities, not hard dependencies. Resolve their current installed skill locations from the runtime catalog or owning plugin; do not hard-code another user's cache path or copy their files into this plugin. Read the selected skill and required references before using it. If unavailable, perform the same bounded public-source research and record the coverage gap.

For Public Equity Investing support, read its router's **Cross-Skill Runtime Contract**, `shared/workflow-source-resolution.md`, and routing playbook/map, plus the selected skill. Resolve only source categories needed for the delegated question. A plugin manifest or saved source preference does not establish callable or entitled access. Here the resolved deliverable is already the house morning email: support workflows inherit that choice, do not repeat format intake, and do not replace it with a dashboard, workbook, standalone event report or portfolio recommendation. Do not inspect saved user context, provision accounts or schedule work as part of this routing.

## Evidence checks

Use public news for discovery and the strongest readable source for each claim. Definitive offer/scheme documents and amendments govern terms; official decisions govern regulatory or court status. A newer commentary article does not supersede a controlling document. Preserve source URL, publication/event dates, retrieval time, relevant page/section, units and security identity. Distinguish announcement, vote/acceptance cutoff, long-stop, effective and settlement dates. Repeated wires are one underlying source.

Dates, voting rules, jurisdictional requirements and review periods must be verified for the actual situation; never hard-code them from memory. Missing information is not an approval, zero cost or adverse event. Rumours remain attributed and unresolved. The 32-name local priority list is retained for additional investigation, not used to exclude newly discovered companies.

## Calendar screening within each researched edition

Unless the user sets another horizon, screen **the edition's local day and the following seven calendar days**, using the edition timezone (Singapore by default). During an early-morning run, pay particular attention to the remaining events that day. Retain each event's original timezone and printed time precision. Research earnings, votes, tender deadlines, court/regulatory dates, effective or settlement dates, index changes and material macro events as relevant; include companies outside the priority list.

Keep useful verified dates in optional `upcoming_events` research records and the editor review. These are **calendar reminders**, not fresh-news items. Do not add a fifth email category or put reminders in the distribution email by default. A newly announced or rescheduled date disclosed within the news window may separately qualify as a sourced update in one of the existing four categories. If the user explicitly requests a calendar in the email, resolve that presentation within the owning morning-note workflow.

An older primary announcement may establish a future event date, but recheck the controlling source and subsequent amendments during this edition. Record the actual check time; never backdate today's retrieval to claim historical availability. A missing check, unresolved conflicting date or vague timing window stays in review, not as a confirmed upcoming date. Do not create placeholder events or infer this year's date from a prior-year calendar. If no verified dated rows are available, leave the array empty and record what was checked or unavailable.

The optional contract uses these fields; [draft-schema.md](draft-schema.md) owns the composer's current exact validation rules:

| Field | Meaning |
| --- | --- |
| `id` | Stable event identifier; keep prior versions when dates or status change. |
| `label`, `company`, `tickers` | Short event label, verified company identity where applicable, and verified identifiers. Macro events may have no company or ticker. |
| `event_type` | Such as earnings, shareholder vote, tender deadline, court hearing, index change, macro release or central-bank decision. |
| `event_date` | Source-backed ISO date or full timezone-aware timestamp. Preserve date-only precision; do not invent midnight. |
| `timezone` | Source event timezone, preferably an IANA name. |
| `time_status` | `confirmed` or `provisional`, describing the stated timing precision. Explain a confirmed day with an unannounced time in notes. |
| `status` | `scheduled`, `completed` or `cancelled`. Preserve completed/cancelled rows for review/history; do not present them as upcoming scheduled events. |
| `source_url`, `source_name` | Direct supporting public source and its name. |
| `source_published_at` | Original source publication timestamp when known; optional. Do not replace it with the check time. |
| `checked_at` | Actual timezone-aware retrieval/verification time during the research run. It may be later than the news cutoff; retain that difference. A current check is not evidence of historical availability, and must never be backdated. |
| `notes` | Material relevance, timing caveats, amended dates, source conflicts or next observation needed. |

The installed `finance-tools` helper `scripts/event_calendar.py` can normalize already researched exact-time events using `{as_of, events}` with `starts_at`, supported `category` and boolean `confirmed`, plus `--days 7`. It does not natively consume the morning-note contract or discover, authenticate or refresh events. Adapt fields explicitly, normalize exact timestamps to a consistent offset before sorting, preserve source/timezone fields, and retain date-only or windowed events separately rather than fabricate a `starts_at`. The Public Equity Investing calendar workbook/ICS helper is also a materializer, not a live calendar source. Neither helper is needed just to produce the existing email.

This workflow creates local research and unsent drafts only. No broker/account action, email sending, calendar subscription, recurring schedule or external write follows from reading these skills.
