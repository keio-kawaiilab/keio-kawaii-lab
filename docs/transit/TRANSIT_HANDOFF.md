# Transit data project handoff

> **READ THIS FIRST IN A NEW CHAT.** This file is the durable handoff for the route-search / timetable / same-train project in `keio-kawaiilab/keio-kawaii-lab`.
>
> Repository state on `main` is the source of truth. If a chat summary or an earlier assistant claim conflicts with the repository, inspect `main`, correct the record, and update this file.

Last reviewed: **2026-09-06 JST**
Repository: `keio-kawaiilab/keio-kawaii-lab`
Default branch: `main`
Public route entry point: `route.html`

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

Verified audit facts from the current official PDF:

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

The production-like Keikyu workflow now contains the full official-PDF and identity/mother-set safety gate and installs Poppler. Do not infer final Keikyu independent-mother-set completion merely from the parser statistics; check the current workflow result and durable audit output first.

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

Current scope metadata marks Toei Asakusa `lineTimetableCoverage` as `exact-independent-1260-verified`. Its cross-operator same-train coverage is still incomplete.

## 7. Current active work: exact Sengakuji reconciliation

The immediate target is **Toei Asakusa <-> Keikyu at Sengakuji**.

Existing Keikyu official connection-timetable PDFs contain an explicit printed column spanning both sides of Sengakuji. Historical production evidence reports:

- weekday official through columns: **297**
- Saturday/holiday official through columns: **284**
- total official through columns: **581**
- historical old-fragment matched-singleton production entries: **494**
  - Toei -> Keikyu: 262
  - Keikyu -> Toei: 232

The old 494 figure is NOT whole-boundary completion; old transit-v2 fragment ambiguity/unavailability prevented all 581 official columns from being materialized.

New work bypasses the historical fragment projection:

- `scripts/audit_toei_sengakuji_official_columns.py`
- `.github/workflows/audit-toei-sengakuji-official-columns.yml`

Policy for this audit:

1. The cross-boundary fact must come from Keikyu's official **same printed column spanning both sides of Sengakuji**.
2. That official column is mapped to a local exact Toei `TrainTimetable` only if calendar + direction + exact boundary event resolve to a singleton.
3. This mapping step does not use historical transit-v2 fragment identity.
4. Time alone and train number alone may never establish cross-operator identity.
5. The Keikyu side still must be linked to the independent Keikyu official-PDF mother-set component before runtime promotion.
6. `runtimeSameTrainPromotions` remains 0 during this audit.

After the Toei side of all official Sengakuji columns is inventoried, link those same official columns to the independent Keikyu mother-set components. Only exact singleton links on both sides may become runtime same-train evidence.

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
