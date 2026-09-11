# スケジュール修正台帳 追補 — 2026-09-11

このファイルは `docs/schedule-audit-fix-log.md` の2026-09-11追補。次回作業開始時は本体とあわせて確認する。

## [本番反映確認済み] CANDY TUNE JAPAN TOUR 2026 -AUTUMN- CANDY CIRCUS 消失・欠落

- 症状: 最新JSON取得失敗時などに使用される公開スナップショット／フォールバックで、CANDY TUNEの2026秋ツアーが途中までしか残らず、今後の公演がカレンダーから消える状態が発生した。
- 原因: 正規データ側は23公演日を保持していた一方、生成された公開スナップショット側で複数日公演の展開が欠落し得る経路があり、欠落した状態でも公開を止める整合性検査がなかった。
- 修正: 正規データから公開スナップショットを再生成し、公式日程23日（2026-08-29〜2026-12-09）を完全な集合として扱うようにした。
- 再発防止: `scripts/guard_candy_tune_tour_integrity.py` を追加・修正し、正規JSONに公式23日がすべて存在すること、および `schedule.html` に当日以降の全ツアーカードが存在することを検査。不足が1日でもあれば公開処理を失敗させる。
- 自動更新への組み込み: `.github/workflows/harden-live-calendar.yml` で、加工前・加工後・HTML生成後にガードを実行。さらに収集更新後も再検査するため、後続の自動更新で再欠落した場合も公開前に止める。
- 関連commit: `4b71b97ec4813258b5ca494843f6d24db90526c3`（初期guard）、`214408ffd8c3ea0fc096f9c51525338eebbec2b5`（hardening組み込み）、`59928b88d094e10f8a61f74a2fb1195a20a52ef4`（collector更新後の再検査）、`8efc897e233ad62cfab8fbae251d9a3d8cd6b016`（公式23日へ訂正）、`346d1cb10155ba069ed0bcef0204ac9aadae6738`（公開HTML欠落時の公開停止）、`e0ccfe22d65063d05caff2cded827a35c50f3144`（guard通過後の公開データ再生成）、`1c4d493b2381f709bc7d5073ddc837587f0104f4`（publication guards再適用）。
- 検証: `guard_candy_tune_tour_integrity.py` の `EXPECTED_DATES` は23日で、最終日は `2026-12-09`。`harden-live-calendar.yml` はHTML生成後に `--html schedule.html` 付きで同ガードを必須実行してからのみpushする。guard通過後の生成commitがmainへ入っている。
- 公開反映確認: 2026-09-11 14:27:50Z開始のGitHub Pages `pages build and deployment` run #2993（run ID `34610267470`）が、main `465b288104d75b6460a23fe55c36b6eb8edf43c1` に対して `success`。このmainは上記修正・再発防止commitをすべて含む。

### 引き継ぎ上の注意

CANDY TUNE 2026秋ツアーについては、日程を手作業で別イベント23件へ複製しない。正規の複数日イベント／公開performance展開を維持し、`guard_candy_tune_tour_integrity.py` を外さない。公式日程が変更された場合のみ、一次情報を確認したうえで `EXPECTED_DATES` と正規データを同時に更新する。
