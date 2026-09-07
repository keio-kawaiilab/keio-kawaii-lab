# Transit data project handoff

> **READ THIS FIRST IN A NEW CHAT.** This file is the durable handoff for the route-search / timetable / same-train project in `keio-kawaiilab/keio-kawaii-lab`.
>
> Repository state on `main` is the source of truth. If a chat summary or an earlier assistant claim conflicts with the repository, inspect `main`, correct the record, and update this file.

Last reviewed: **2026-09-07 JST**
Repository: `keio-kawaiilab/keio-kawaii-lab`
Default branch: `main`
Public route entry point: `route.html`

Latest work checkpoint: `work/sengakuji-exact-reconciliation-20260907`, based on
`39791a0d5e63cac5fc69e66d00aca1931c890138`. The work below is an audit-only branch
checkpoint until merged; it is NOT a claim of production deployment. Do not
reuse the earlier unpushed `a7111c8` time-proximity implementation.

**Save checkpoint:** earlier commits `51f48773` and `a86bbedc` were local only:
CLI push failed with `could not read Username for 'https://github.com'`.
The already-connected GitHub integration was subsequently confirmed available;
the CLI failure does NOT mean the user must configure another credential.
Persistence target for this newer checkpoint is the isolated remote branch
`work/sengakuji-exact-reconciliation-20260907`; verify its remote ref when
resuming. Remote snapshot base checked during this investigation:
`83bd4fc88cbc690ac1bfaf2b7bb3e196cf0ec752`. Changes since the local base affect
only unrelated live-event/schedule/ticket files and must be preserved.
No main merge, deployment, credential substitution or writer dispatch is allowed
by this audit checkpoint. Local worktree:
`/workspace/scratch/e5a852942b1f/transit-work`.

**CRITICAL CORRECTION (read before using older counts):** the 581 printed
connection columns are NOT 581 proven through trains. Four holiday columns
explicitly connect to another train from Nishimagome. Same-column alignment
alone does not establish physical identity. See section 7's new checkpoint.

## 1. Non-negotiable meaning of 「○○系統」

「○○系統を見て」は、○○へ入る列車だけを見るという意味ではない。

1. ○○は、実際の同一列車直通関係でつながる鉄道路線グラフの seed としてだけ使う。
2. 実際の same-train through-service edge を再帰的にたどり、transitive closure（連結成分）を作る。
3. その連結成分に含まれる **全路線の全列車** を監査・収集対象にする。
4. seed 路線を一度も通らない列車も対象。平日/土休日、上下方向、支線、線内完結、途中始発/終着も除外しない。
5. 真の強制乗換境界までグラフを拡張する。
6. ただし、連結成分に属することと「この特定列車が乗換なし」は別問題。0回乗換にするには、その予定列車の同一物理列車 identity が厳密に証明されている必要がある。

例: 「13号線系統」には、副都心線を通らない **東横線始発→みなとみらい線** の列車も含める。

## 2. Exact same-train policy: fail closed

同一列車 identity は必ず fail closed。

- 時刻が近いだけで同一列車にしない。
- 行先が同じ/似ているだけで同一列車にしない。
- 曖昧な列車番号一致だけで同一列車にしない。
- PDFの別ページに同じ printed train number があっても、自動結合しない。
- 連絡時刻表の同じ縦列だけで直通としない。継続矢印と西馬込分岐欄を確認し、別列車への接続を除外する。
- 境界 metadata が `verified` でも、それは物理的/運用上の直通可能性を示すだけ。特定列車の continuation 証明ではない。
- identity が証明できない境界は、route runtime では乗換として扱う。
- 解析不能セル・未解決列車を黙って捨てない。件数と中身を監査可能な形で残す。

## 3. Runtime architecture

`route.js` loads, among other data:

- `data/transit/manifest.json`
- `data/transit-v2/manifest.json`
- `data/transit-v2/runtime-same-train.json`
- `data/transit/keisei/official-network.json`

`route-core.js` normally increments transfers at a railway boundary. It suppresses that increment only when the strict same-train resolver proves exact identity.

Known strict identity sources are exact network-trip identity and exact pre-generated runtime same-train pairs. Boundary verification alone must never become runtime 0-transfer identity.

## 4. Keisei connected component status

**京成系統: INCOMPLETE / 未完成。** Do not call it complete.

The Keisei-led exact network remains highly complete for trains whose mother source is the Keisei official one-train source, but whole-component completion requires independent all-train mother sets for every connected member railway and exact cross-boundary identities.

Current scope truth is in:

- `data/transit/keisei/system-scope.json`

The component currently includes Keisei core lines, Hokuso, Shibayama, Toei Asakusa, and Keikyu Main/Airport/Kurihama/Zushi. Keisei Kanamachi and Keikyu Daishi remain excluded because no same-train through edge to the component is verified.

## 5. Independent Keikyu official-PDF mother-set work

The Keikyu official full-line PDF is now parsed independently of the Keisei mother set.

Current **printed-calendar + page/section/column** audit (2026-09-07):

- Source SHA256: `e10b1c6efd92f40b0dae6d712b65c2391584b9134cd653c74fe78548ad681b63`
- PDF pages: **145**; retained calendar-labelled pages: **127**, sections: **156**
- Geometry column fragments: **3,928** (weekday 1,935; holiday 1,993)
- Train-bearing fragments: **2,968**; structural blank slots: **960**, retained separately
- Source time cells: **64,890** = resolved **63,685** + unresolved **1,205**
- Calendar-excluded PDF pages: **56, 58, 68, 70, 74, 77, 145**; do not infer their calendars
- Raw complete previous-publication references: **298**; same-printed-calendar references: **253**
- **45** target references remain excluded/missing from the literal-calendar dataset
- Verified reference graph: **253** edges (weekday 93; holiday 160), **506** nodes,
  no branching, multiple predecessors, cycles, or issues
- Candidate physical-train components: **2,715** = 253 joined + 2,462 singleton
- `coverageComplete = false`; `runtimeSameTrainPromotions = 0`

Durable full component/blank inventory:
`docs/transit/keikyu-independent-mother-set-audit.json`.
These are candidate components within retained parsed coverage, NOT a completed
independent all-train mother set. Excluded pages and unresolved cells block completion.

**Historical page-only audit below is superseded.** Its counts must not be used
as current coverage or compared as if the extraction scope were unchanged:

- PDF pages: **145**
- in-scope timetable pages: **132**
- page-local column fragments: **3,336**
- source time cells: **78,400**
- resolved time cells: **74,073**
- unresolved time cells: **4,327**, preserved rather than dropped
- complete official `前の掲載ページ + 列車番号` references: **387**
- uniquely resolved official references: **387 / 387**
- missing printed page numbers: **0**
- identity reference graph: 387 edges, 774 nodes, no branching, no multiple predecessors, no cycles, no issues
- the new cross-page audit layer still has `runtimeSameTrainPromotions = 0`

Key files include:

- `scripts/keikyu_official_pdf.py`
- `scripts/build_keikyu_official_stop_times.py`
- `scripts/verify_keikyu_official_stop_times.py`
- `scripts/audit_keikyu_previous_publication_refs.py`
- `scripts/build_keikyu_cross_page_identity_audit.py`
- `scripts/verify_keikyu_cross_page_identity_audit.py`
- `scripts/build_keikyu_independent_mother_set_audit.py`
- `scripts/verify_keikyu_independent_mother_set_audit.py`

The 2026-09-07 branch repairs schema drift: stop-time verifier requires v4;
independent mother builder/verifier require the calendar-aware v3 graph and
source hash agreement. Graph verification recomputes topology rather than
trusting producer issue arrays. The writer workflow now filters references by
literal calendar before building the graph. The read-only calendar audit
workflow also builds/verifies the mother set and Sengakuji reconciliation.
Do not infer CI or production success merely from local verification.

## 6. Toei Asakusa independent mother set: VERIFIED

The Toei Asakusa train-timetable mother set has been audited independently of the Keisei mother set and verified by CI.

Durable summary:

- `docs/transit/toei-asakusa-independent-mother-set-audit.json`

Verified counts:

- exact TrainTimetable trips: **1,260**
- unique timetable IDs: **1,260**
- unique calendar+train IDs: **1,260**
- weekday trips: **651**
- Saturday/holiday trips: **609**
- stations: **20**
- stop records: **16,826**
- connections: **15,566**
- internal-destination trips: **504**
- external-destination trips: **756**
- raw non-monotonic trips: **12**
- all 12 are exactly one legitimate 23:xx -> 00:xx service-day midnight wrap
- unsafe time regressions: **0**
- audit issues: **0**
- runtime same-train promotions from this audit: **0**

Important time rule: the compact Toei source stores clock-of-day minutes modulo 1440. Chronology validation may add +1440 only for one tightly constrained 23:xx -> 00:00-02:00 wrap; raw values are preserved. Any other decrease remains a hard failure.

Use `audit_toei_asakusa_service_day.py` / `verify_toei_asakusa_service_day.py`
for the current check. The older base audit deliberately reports 12 raw clock
regressions and is not the final service-day verification. The Sengakuji
reconciliation now reruns the service-day audit on its actual Toei input.

Current scope metadata marks Toei Asakusa `lineTimetableCoverage` as `exact-independent-1260-verified`. Its cross-operator same-train coverage is still incomplete.

## 7. Current active work: exact Sengakuji reconciliation

The immediate target is **Toei Asakusa <-> Keikyu at Sengakuji**.

Existing Keikyu official connection-timetable PDFs contain an explicit printed column spanning both sides of Sengakuji. Historical production evidence reports:

- weekday printed connection candidate columns: **297**
- Saturday/holiday printed connection candidate columns: **284**
- total printed connection candidate columns: **581** (includes 4 transfers)
- historical old-fragment matched-singleton production entries: **494**
  - Toei -> Keikyu: 262
  - Keikyu -> Toei: 232

The old 494 figure is NOT whole-boundary completion; old transit-v2 fragment ambiguity/unavailability prevented all 581 official columns from being materialized.

New work bypasses the historical fragment projection:

- `scripts/audit_toei_sengakuji_official_columns.py`
- `.github/workflows/audit-toei-sengakuji-official-columns.yml`

Policy for this audit:

1. Same printed column alone is insufficient. Require an explicit boundary continuation arrow and an empty Nishimagome branch cell on a located branch row; reject another train number plus a Nishimagome departure as a transfer. Missing/ambiguous markers fail closed.
2. That official column is mapped to a local exact Toei `TrainTimetable` only if calendar + direction + exact boundary event resolve to a singleton.
3. This mapping step does not use historical transit-v2 fragment identity.
4. Time alone and train number alone may never establish cross-operator identity.
5. The Keikyu side still must be linked to the independent Keikyu official-PDF mother-set component before runtime promotion.
6. `runtimeSameTrainPromotions` remains 0 during this audit.

After the Toei side of all official Sengakuji columns is inventoried, link those same official columns to the independent Keikyu mother-set components. Only exact singleton links on both sides may become runtime same-train evidence.

### 2026-09-07 independent reconciliation checkpoint

Implemented `scripts/audit_sengakuji_independent_reconciliation.py`.
Full, unprojected **581** official columns were re-extracted from the weekday
and holiday connection PDFs. Source hashes, URLs, page/column geometry, local
Toei IDs, Keikyu component candidates and all unresolved results are saved in
`docs/transit/sengakuji-independent-reconciliation-audit.json`.

| Audit status | Columns |
| --- | ---: |
| Both independent local candidates singleton | 301 |
| Toei singleton, Keikyu components ambiguous | 238 |
| Toei singleton, Keikyu component unmatched | 6 |
| Toei local trips ambiguous | 32 |
| Toei local trip unmatched | 4 |
| Total | 581 |

Toei-only stage: **545 singleton / 32 ambiguous / 4 unmatched**, no duplicate
target conflicts. **301 is NOT newly deployed through services**, and is NOT
comparable to the historic projected 494: the input identity model differs.
All 581 stay audit-only; no runtime DB or route code changed in this checkpoint.

**Superseded assumption:** this baseline treated same-column alignment as a
crossing fact; that is unsafe for four printed transfer connections. The new
boundary-marker audit below must be applied before interpreting any local match.
Exact calendar + station event + boundary minute only nominate a local
Keikyu component. Arrival and departure are not interchangeable. This stage
does not merge ambiguous components, use close times, or select by train number.
Unsupported official provenance/geometry, duplicate column IDs and duplicate
local targets are rejected or demoted. Full mother-set completeness and
corroborating identity/coverage review remain required before runtime promotion.

**Historical next action (now investigated below):** inspect the 238 ambiguous Keikyu matches using the retained
component IDs, official page/section/column geometry and multi-station sequence
evidence. Distinguish duplicate publication from genuinely distinct trains;
do not merge because boundary times or numbers coincide. Then address the six
Keikyu misses, 32 Toei ambiguities, four Toei misses, excluded calendars and
1,205 unresolved full-PDF cells. Keep all negative cases visible.

Useful next-investigation split: all **238** Keikyu ambiguities are
**Keikyu -> Toei** (weekday 105, holiday 133). For example candidate
`keikyu-connection-pdf:c09b488cca4a7ddc6cc5d4c4` maps the exact 04:59
arrival to separate `p037:s00:c02` and `p067:s01:c01` components, both
printed `403T`. Repeated publication is a hypothesis to investigate, NOT a
same-train proof or permission to union them.

### 2026-09-07 continuation-marker / reciprocal-publication checkpoint

New audit-only generators and durable reports:

- `scripts/audit_keikyu_reciprocal_publication.py`
- `scripts/audit_sengakuji_published_sequences.py`
- `scripts/test_keikyu_reciprocal_publication.py`
- `docs/transit/keikyu-reciprocal-publication-audit.json`
- `docs/transit/sengakuji-published-sequence-audit.json`

The previous-reference row in connection panels is BELOW their own header.
The old preceding-header extractor missed these repeat-publication references.
Require both source `次の掲載ページ` and target `前の掲載ページ` to point back,
one literal train number on uniquely mapped printed pages, matching literal
calendars, one-to-one links and no cycles. This proves **repeat publication**,
not permission to concatenate overlapping stop sequences.

- Metadata: all **3,928** parsed columns rechecked against actual PDF geometry.
- **370** reciprocal links: weekday **148**, holiday **222**.
- Of 418 in-section previous references, **24** lack a reciprocal next page and
  **24** have an excluded/unmapped/ambiguous page; all remain rejected.
- Combining these links with the existing mother set gives **2,345** publication
  groups, not a count of complete physical trains.
- Reciprocal links alone resolve 134 of the former 238 Keikyu ambiguities.
  The other 104 include genuinely different opposite-direction trains at the
  same minute. Ordered, exact multi-station sequences distinguish them; they
  are NOT merged. All 238 now have unique local published-sequence matches.
- All 32 former Toei ambiguities are distinguishable by exact ordered station
  sequences. Of these, 29 also have a Keikyu match; 3 remain among the 9 misses.

Current inventory after explicit marker and both-local sequence checks:

| Result | Columns |
| --- | ---: |
| Explicit continuation; both local published sequences singleton | 568 |
| Explicit continuation; Keikyu independent source still unmatched | 9 |
| Explicit connection to another Nishimagome-origin train; NOT through | 4 |
| Total source candidate inventory | 581 |

**577** have an explicit continuation arrow, **4** instead have another train
number and a populated Nishimagome departure. The four are all holiday
Keikyu -> Toei. Arrival/departure coincidence is NOT proof of continuity:

| Holiday PDF page | Keikyu Sengakuji arrival | Other train's Nishimagome departure | Toei Sengakuji departure | Printed boundary number |
| --- | --- | --- | --- | --- |
| 3 | 09:42 | 09:29 | 09:43 | 931N |
| 9 | 19:45 | 19:31 | 19:45 | 1985K |
| 10 | 21:05 | 20:51 | 21:05 | 2033N (suffix separately printed) |
| 10 | 23:19 | 23:08 | 23:22 | 2381K |

Source: https://www.keikyu.co.jp/ride/kakueki/pdf/other_holiday.pdf.
Visually checked page 3: arriving Keikyu 815A terminates at Sengakuji while
931N comes from Nishimagome. All four branch-row times and marker geometries
are retained in the report. Toei local corroboration uses the whole published
station sequence and Nishimagome departure, NOT fuzzy/stripped train numbers
(2033N's local ID is `2033Nb.SaturdayHoliday`). The four have Sengakuji as an
interior Toei stop; they are not missing/corrupt ODPT trips. The old 494-entry
projected evidence contains none of these four boundary numbers, but this is
not a complete runtime provenance audit.

The **9 remaining Keikyu misses are all weekday**:

- Eight northbound arrivals **18:07, 18:14, 18:18, 18:22, 18:28, 18:34,
  18:40, 19:26**, on weekday connection PDF page 8. Matching printed times
  occur on full PDF pages **56/58/74**, excluded for unproven literal calendar.
  This is a coverage diagnostic, not authority to infer the excluded calendar.
- One southbound **00:18 arrival -> 00:20 departure -> Shinagawa 00:22**,
  weekday connection PDF page 10. Full PDF page 36's lower header has a final
  `↓` at x=444.33 after its last literal `2422` at x=413.16. The section-1 grid
  stops at column 22/x=413.181, dropping this continuation-only trailing column.
  The upper header explicitly prints 2252H at x=444.34; full PDF page 76 also
  prints that train, but its Keikyu station rows lie beyond the retained section.
  Fix grid coverage with source-backed continuation slots and negative tests;
  do not join trains merely because their x coordinates or times coincide.

No production DB, runtime resolver, main merge or deployment changed.
`coverageComplete=false`, `runtimeSameTrainPromotions=0` remain mandatory.
**Next:** repair trailing-arrow column coverage; establish literal calendars
for excluded pages without inference; account for 1,205 unresolved cells;
then rebuild/reverify mother and boundary audits. The old broad candidate
extractors still return transfer columns intentionally for inventory: never
promote their results without the new boundary-marker gate.

## 8. Remaining component blockers

Do not mark 京成系統 complete until at least these are resolved:

1. Finish and durably verify the independent Keikyu mother set for Main/Airport/Kurihama/Zushi.
2. Complete exact Sengakuji identity reconciliation between Toei's verified 1,260-trip mother set and the independent Keikyu mother set.
3. Complete exact Oshiage identity reconciliation for the independently verified Toei mother set against the Keisei/Hokuso side.
4. Verify all-train completeness for Hokuso from an independent Hokuso official mother source rather than only Keisei-led projection.
5. Verify all-train completeness for Shibayama from the current official timetable.
6. Add positive runtime regressions for exact external-only through trains and negative regressions for terminating/non-through trains.

## 9. Whole-component completion gate

Do not mark any 「○○系統」 complete until all of the following are true:

- the recursively connected same-train railway component has been enumerated from current official evidence;
- every member railway/line has a complete mother set for weekdays and holidays, both directions, branches, line-only and terminating services;
- source-cell/train counts are accounted for and unresolved data is visible rather than silently dropped;
- exact physical-train identity is unified where official evidence proves it;
- unresolved/ambiguous identity remains a transfer;
- route-search positive and negative regressions pass;
- the relevant current CI run has been checked and is successful.

## 10. Handoff maintenance rule

Whenever substantial transit work is committed, update this file when any of these change:

- current target/system;
- completion status;
- safety/identity policy;
- active generator/workflow files;
- known gaps or corrections;
- exact next action needed to resume.

A new chat should be able to resume by reading this file plus the current files it names, without asking the user to restate the project rules.

## 11. Latest verification and resumption commands

Local verification on the 2026-09-07 checkpoint:

- `python3 -m unittest discover -s scripts -p 'test_keikyu_*.py'`: **123 passed** (27 new reciprocal/sequence/transfer tests).
- `python3 scripts/test_sengakuji_independent_reconciliation.py`: **12 passed**.
- `python3 -m unittest discover -s scripts -p 'test_toei_*.py'`: **9 passed**.
- Route runtime same-train, route-core, transfer-rules and transfer-block JS suites: **passed**.
- Actual PDF stop-time verifier, calendar reference graph verifier, independent
  Keikyu mother verifier and 581-column reconciliation: **passed**.
- Existing old-schema Keikyu test fixtures were upgraded, not safety checks relaxed.
- Whole-repository Python discovery is **NOT green**: 267 tests at the time
  of the broad run, one unrelated ticket-history assertion failure and 32
  errors including unavailable `requests` dependencies. Do not claim all-project success.
- Remote CI result for this branch: **not verified**. The earlier CLI push
  was blocked by missing CLI authentication; use the existing connected GitHub
  integration for the isolated audit snapshot. The writer workflow was
  edited but never executed. Do not claim its production refresh succeeded.
- Existing Zushi calendar cross-page dry-run: **0 additional proofs**, with
  163 unresolved sources still rejected. It wrote scratch audit output only;
  existing production evidence was not edited.

Reproduce the independent audit using one downloaded official full PDF:

```sh
python3 scripts/build_keikyu_official_stop_times.py --pdf /tmp/keikyu-schedule-all.pdf --output /tmp/keikyu-stops.json
python3 scripts/verify_keikyu_official_stop_times.py /tmp/keikyu-stops.json
python3 scripts/audit_keikyu_previous_publication_refs.py --pdf /tmp/keikyu-schedule-all.pdf --output /tmp/keikyu-refs-raw.json
python3 scripts/filter_keikyu_previous_refs_by_calendar.py /tmp/keikyu-stops.json /tmp/keikyu-refs-raw.json --output /tmp/keikyu-refs-calendar.json
python3 scripts/build_keikyu_calendar_cross_page_identity_audit.py /tmp/keikyu-stops.json /tmp/keikyu-refs-calendar.json --output /tmp/keikyu-graph.json
python3 scripts/verify_keikyu_cross_page_identity_audit.py /tmp/keikyu-graph.json
python3 scripts/build_keikyu_independent_mother_set_audit.py /tmp/keikyu-stops.json /tmp/keikyu-graph.json --output /tmp/keikyu-mother.json
python3 scripts/verify_keikyu_independent_mother_set_audit.py /tmp/keikyu-mother.json
python3 scripts/audit_sengakuji_independent_reconciliation.py /tmp/keikyu-stops.json /tmp/keikyu-graph.json --output /tmp/sengakuji-reconciliation.json
```

The last command fetches both official connection PDFs. Compare source hashes
before interpreting count changes. The read-only calendar workflow retains the
full stop dataset, mother inventory and reconciliation as downloadable artifacts.

Continue with the new safety gate (the baseline is an inventory, not identity):

```sh
python3 scripts/audit_keikyu_reciprocal_publication.py --pdf /tmp/keikyu-schedule-all.pdf --stops /tmp/keikyu-stops.json --graph /tmp/keikyu-graph.json --output /tmp/keikyu-reciprocal.json
python3 scripts/audit_sengakuji_published_sequences.py --stops /tmp/keikyu-stops.json --graph /tmp/keikyu-graph.json --mother /tmp/keikyu-mother.json --reciprocal /tmp/keikyu-reciprocal.json --baseline /tmp/sengakuji-reconciliation.json --output /tmp/sengakuji-sequences.json
```

The read-only calendar workflow now runs both new generators and retains their
full reports. A changed connection-PDF hash fails and requires a new baseline;
do not compare snapshots from different timetable revisions silently.
