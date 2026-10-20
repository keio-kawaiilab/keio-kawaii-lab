# Official-source maintenance — 2026-10-20 JST

Rechecked five group and central KAWAII LAB. home, news and schedule pages, current main, source discovery/publication diagnostics, Actions and actual browser-rendered calendar. No X API used.

## Persistent changes

1. CUTIE STREET Hiroshima retained Pia lot 88970: recover exact per-day venue/open/start facts from https://cutiestreet.asobisystem.com/live_information/detail/40366 (11/14, OPEN 16:00, START 18:00) and /40367 (11/15, OPEN 14:30, START 16:30), also confirmed by https://cutiestreet.asobisystem.com/news/detail/92733. Preserve acquisition ID, sale fields, original links and history. Fix the source row before performance consolidation, not generated HTML alone. Other lots/dates remain untouched.
2. FRUITS ZIPPER FANCLUB LIVE -じょい！×３-: add verified 2026-11-08 Tokyo Garden Theater, OPEN 13:30 / START 15:00, from https://fruitszipper.asobisystem.com/news/detail/93201. That article explicitly says application details will follow: no invented application dates or band. The known-correction path is idempotent and does not duplicate a collector row carrying the same announcement.
3. Publication audit: source observation `リセール` and normalized `公式リセール` describe the same verified resale window. Allow only that explicit alias with resale-channel and original-article provenance; still require exact occurrence/date/time/window. https://fruitszipper.asobisystem.com/news/detail/88139 confirms the windows. Missing/changed offers and source failures still degrade the report. No audit disabled.

## Verification

- 63 relevant Python tests: passed, one historical-event test skipped by existing test design.
- Rebuilt schedule and public performance model; JavaScript syntax, band grouping, scope and canonical performance runtime checks passed.
- CANDY TUNE 2026-10-20 online benefit remains a single public card starting 17:00 with first-come band through 17:00, matching https://candytune.asobisystem.com/live_information/detail/46277 and https://sukisuki-shop.com/goods/6500000004623.
- Newly announced CUTIE STREET Sano Aika KAWAII LAB. FC presale is already in current acquisition data: https://kawaiilab.asobisystem.com/news/detail/92827, 10/20 12:00–10/25 23:59, event 11/26 19:00.
- FRUITS ZIPPER charity concert announcement https://fruitszipper.asobisystem.com/news/detail/93365 is already represented; its lineup assigns the KAWAII LAB. groups to 2027-01-19, not 01-20.

Publication is delegated to the existing audited distributed calendar workflow against latest main; this source commit does not overwrite concurrent generated data. Pending discovery articles and unrelated legacy warnings are not represented as fully resolved by these targeted changes.
