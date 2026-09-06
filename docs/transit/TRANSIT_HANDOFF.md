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

**京成系統: INCOMPLETE / 未完成。**

Do not call it complete.

The Keisei-led exact network is highly complete for trains whose mother source is the Keisei official one-train source, but the architecture historically used that Keisei source as the mother set. Therefore it does not by itself prove complete coverage of external-only services, such as trains wholly on the Keikyu side or other component-member services that never touch Keisei.

Important existing file:

- `scripts/build_keisei_extended_network.py`

Its Keisei-led source architecture is the reason whole-component completion must not be inferred merely from supported railway counts or route signatures.

## 5. Current active work: independent Keikyu mother set

The current priority is to ingest **all current Keikyu official timetable columns independently of the Keisei mother set**.

Key files:

- `scripts/keikyu_official_pdf.py`
  - downloads the official full-line timetable PDF
  - detects strict page-local physical train columns from PDF geometry
  - anonymous published columns are valid local columns but never cross-page identity by themselves
- `scripts/audit_keikyu_official_columns.py`
  - page/column coverage audit
- `scripts/audit_keikyu_station_time_resolution.py`
  - resolves station + arrival/departure semantics without same-train inference
  - `resolve_page(..., include_records=True)` is the semantic source for generation
- `scripts/build_keikyu_official_stop_times.py`
  - builds page-local stop-time fragments
  - fragment identity = exact PDF `page + column`
  - preserves `printedTrainNumber` only as metadata
  - preserves unresolved cells
  - full generated JSON is intended for ephemeral CI/research use, not checked into the public repo
- `scripts/verify_keikyu_official_stop_times.py`
  - fail-closed structural/accounting verifier
- `scripts/test_keikyu_official_stop_times.py`
  - regression tests for page-column grouping, anonymous columns, no cross-page train-number merge, unresolved preservation, printed row order, and unknown-column failure

The generated dataset explicitly requires:

- `printedTrainNumberMayJoinPages = false`
- `anonymousColumnMayJoinPages = false`
- `clockTimeProximityMayJoinFragments = false`
- `destinationMayJoinFragments = false`
- `crossPageIdentityEstablished = false`
- `runtimeSameTrainPromotions = 0`

Until a separate official-evidence identity layer proves continuation, these values must remain fail-closed.

## 6. Known correction from 2026-09-06

An earlier assistant report claimed that the new full-PDF stop-time builder/verifier had already been wired into `.github/workflows/update-keikyu-official-through-evidence.yml`.

Repository inspection on 2026-09-06 showed that this was **not true**: the production-like Keikyu update workflow still ran the older official through-evidence pipeline and did not yet invoke `build_keikyu_official_stop_times.py` / `verify_keikyu_official_stop_times.py`.

The repository is authoritative. Any future assistant must not repeat the earlier claim unless the workflow on `main` actually contains those quality-gate steps.

## 7. Immediate next work

1. Promote the full Keikyu PDF parser/builder/verifier from experiment-only tooling into a mandatory quality gate of the official Keikyu update workflow.
2. Keep the full generated stop-time JSON under `/tmp` or another ephemeral CI path; do not add the raw full timetable DB/PDF to the public repository merely for convenience.
3. Establish cross-page physical-train continuation only from explicit official evidence. Same train number + adjacent page + compatible time is only a candidate, never proof by itself.
4. After Keikyu has an independent mother set, inventory the other railways in the same connected component (including Toei Asakusa and other connected member lines) so trains that never touch Keisei are not omitted.
5. Add route regressions for proven external-only same-train cases and negative terminating/non-through cases before runtime promotion.

## 8. Whole-component completion gate

Do not mark any 「○○系統」 complete until all of the following are true:

- the recursively connected same-train railway component has been enumerated from current official evidence;
- every member railway/line has a complete mother set for weekdays and holidays, both directions, branches, line-only and terminating services;
- source-cell/train counts are accounted for and unresolved data is visible rather than silently dropped;
- exact physical-train identity is unified where official evidence proves it;
- unresolved/ambiguous identity remains a transfer;
- route-search positive and negative regressions pass;
- the relevant current CI run has been checked and is successful.

## 9. Handoff maintenance rule

Whenever substantial transit work is committed, update this file when any of these change:

- current target/system;
- completion status;
- safety/identity policy;
- active generator/workflow files;
- known gaps or corrections;
- exact next action needed to resume.

A new chat should be able to resume by reading this file plus the current files it names, without asking the user to restate the project rules.
