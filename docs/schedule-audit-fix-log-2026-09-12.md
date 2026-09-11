# スケジュール総点検 修正台帳 2026-09-12 追補

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
