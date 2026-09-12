# スケジュール総点検 修正台帳 2026-09-12 追補

## 2026-09-12 再消失: ブラウザの公演整理が受付終了と公演削除を混同

- 調査基点: `eca6f9ef1711b58cb63c926c2f2abdf8baf03475`。データに23日存在するが、実際の `prepare()` 実行後に9/19などが消えることを再現。
- 原因: 公演の関連URL群にぴあがあると公式FC/リセールもぴあ判定。`expandCanonicalOffers()` で分けた公演本体と受付を `mergePiaDuplicates()` がlot単位で再統合し、受付期限・FC除外フィルタが公演も削除していた。
- 前回のチェックの限界: 入力日付の存在と静的HTMLしか確認せず、prepare・絞り込み・カレンダー・詳細カードまで実行していなかった。「再発防止完了」の説明は不十分だった。
- 修正: `guard_performance_runtime.py` で公演本体と受付に役割を付与。公演本体から受付期限を切り離し、canonical公演・受付を旧収集行の再補完/lot統合/終了受付削除から除外。公演翌日以降は通常どおり非表示。終了受付は履歴に残し、申込帯は期限どおり非表示。
- 公式/プレイガイド判定は明示されたproviderを優先。offerにはそのofferのURLだけを持たせ、他社URLを継承しない。
- 関連修正: `fix_missing_application_start_ui.py` がscript内のHTML文字列まで静的カードとして書き換え、受付状態を「開始日時未取得」に固定していた。静的処理はscript外だけに限定し、runtime関数は完全な実装へ復元。
- 継続適用: `fix_schedule_shell.py` と最終公開境界 `strip_schedule_explanations.py` に接続。最終公開境界で `test_performance_runtime.js` を実行し、表示後の欠落時は公開を失敗させる。
- 検証: 修正前HTMLでは9/19消失で新テスト失敗。修正後は今後18日すべての表示モデル、詳細カード、カレンダー生成、CANDYフィルタ、最新JSON成功/失敗時のsnapshot表示を検証。合成例で同一lotの別日/昼夜公演、FC判定、終了履歴/未来リセール、当日表示/翌日削除を検証。公開後の確認結果は次の追記を参照。
- 次の作業者: 入力23日だけで正常判断しない。必ず `node scripts/test_performance_runtime.js` を実行する。旧公演/チケット混在モデルに戻さない。

### 本番反映確認

- 修正コミット: `f8d1c445450142459e34b87c6e5290afd02244f8`。
- CI成功: `Schedule shell build regression` run `34666038550`、`Harden live calendar` run `34666038562`、`Apply canonical special-event entities` run `34666038526`、`Special event entity regression` run `34666038580`。
- 自動再生成後commit: `28a1a55f3ee2b4e70b568e9deae55624fe7ee060`。GitHub Pages run `34666055957`: completed / success。
- 公開URLからschedule.htmlとlive-events.jsonを取り直し、その取得内容を `test_performance_runtime.js` に渡して成功。今後18日分のprepare/詳細カード/カレンダー出力、snapshot/latest/offline経路を確認。実ブラウザの目視検査ではなく、公開コードをNode VMで実行した表示処理テストである。
- 状態: 本番反映確認済み。この修正では公開データの公演日程を手動追加・削除していない。

本ファイルは `docs/schedule-audit-fix-log.md` の 2026-09-12 追補。次回作業時は本ファイルと本体台帳を両方読むこと。

## 緊急修正: CANDY TUNE JAPAN TOUR 2026 - AUTUMN 再消失

### 症状
- 正規の `data/live-events.json` は CANDY TUNE 2026秋ツアー全23公演を保持しているのに、公開ページでツアーが消えることがあった。
- `live-runtime-fallback.js` は `eventCount: 23` のまま、`eventDates` が6公演（2026-08-29 / 08-30 / 09-04 / 09-09 / 09-10 / 09-19）しかなく、最新JSON取得失敗時に古いfallback表示へ落ちると後続公演が消える状態だった。

### 根本原因
- `live-runtime-fallback.js` が正規JSONと継続同期されず、2026-08-23時点の部分的な静的状態で止まっていた。
- 既存の CANDY TUNE integrity guard は正規JSONと生成HTMLを検査していたが、実際の障害時表示に使う `live-runtime-fallback.js` を検査していなかった。
- そのため、正規データが23公演でも、古いfallbackだけが6公演のまま本番へ残る経路があった。

### 修正
- `scripts/build_live_runtime_fallback.py` を新設し、`data/live-events.json` からfallbackを毎回全件再生成するようにした。
- `scripts/guard_candy_tune_tour_integrity.py` に `--fallback` 検査を追加し、fallbackにも公式23公演がすべて存在することを必須化した。
- `.github/workflows/harden-live-calendar.yml` を更新し、公開前および競合再試行時にfallbackを再生成し、正規JSON・生成HTML・fallbackをまとめて検証するようにした。欠損時はpushしない。
- `.github/workflows/refresh-live-runtime-fallback.yml` を新設し、`data/live-events.json` 更新ごとにfallbackを同期するようにした。main競合時は最新mainへ戻して再生成し、最大4回再試行する。

### 検証
- `Harden live calendar` run `34653735378`: completed / success。
- 生成コミット `6005d2fdc103993b4fb0a2006670c7048c4d328a`: `Repair and synchronize physical schedule items`。
- 同コミット系統の `Harden live calendar` run `34653810494`: completed / success。
- 再生成後の `live-runtime-fallback.js` blob: `4b87a5e1fae98c805bb4bbeda14587e15a096893`。正規カレンダー全件から生成された状態。
- 更新後guardは、正規データ23/23・runtime fallback 23/23・生成HTMLの必要な今後のツアーカードが揃わなければ失敗する。
- GitHub Pages `pages build and deployment` run `34653909548` は head `6005d2fdc103993b4fb0a2006670c7048c4d328a` で completed / success。本番デプロイ確認済み。

### 引き継ぎ
- CANDY TUNEツアーのfallbackを部分的な静的データとして手動維持しない。必ず正規 `data/live-events.json` から生成する。
- 公式23公演のうち1公演でも正規データ・fallbackから欠けた場合は公開を止める。
- 次の通常修正対象は本体台帳どおり P2-11「182イベント掲載中」の件数定義不一致。

## 再発防止強化: 欠損した最新JSONをブラウザで採用しない

### 追加で判明した表示経路
- 公開HTMLの静的バックアップが正常でも、ページ表示後に `data/live-events.json` を取得して無条件で表示を置き換えていた。
- そのため、既存の公開前チェックを通らない古い手動・一回限りの更新経路が欠損JSONをmainへ入れた場合、次の自動修復までの間だけツアーが消える余地があった。

### 再発防止
- `scripts/guard_schedule_latest_data_loading.py` にブラウザ側の内容検査を追加した。
- 最新JSONの `publicEvents`（未生成時のみ `events`）に、公式CANDY TUNE秋ツアー全23日程が存在する場合だけ表示を置き換える。
- 1日でも欠けているJSONは採用せず、検証済みの静的バックアップ表示をそのまま維持する。
- 既存の公開前チェック、runtime fallback全件同期、ブラウザ採用前チェックの3段階で欠損表示を防ぐ。
- `scripts/test_guard_schedule_latest_data_loading.py` と `scripts/test_schedule_latest_data_guard.js` をCIへ追加し、ガードの挿入・旧ページからの更新・冪等性・未知の実装形への安全停止に加え、実データは通過し1日欠損データは拒否されることを確認する。
