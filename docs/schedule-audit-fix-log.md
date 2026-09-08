# スケジュール総点検 修正台帳

最終更新: 2026-09-08
現在の作業ブランチ: `fix/schedule-audit-p0-2-christmas-venue`

## 引き継ぎルール
- 別チャットでは最初にこのファイルを読む。
- 1件ずつ `調査中 → 修正済み → 検証済み` の順で進める。
- 修正したファイル名・原因・確認内容を必ず追記する。
- 原則として未検証の変更を `main` に入れない。
- 各項目は、可能なら公式一次情報の確認内容・PR番号・CI結果まで残す。

## 修正対象

1. [検証済み] P0 SWEET STEADY 9/5・9/7・9/14 リリースイベントの情報混在
   - 原因: 3日分を1つの正規イベント系列に統合したあと、日付固有の `salesStartTime` / `gatheringTime` / `startTime` / `numberedCallTimes` まで親レコードへ残り、表示時に全日へ継承されていた。
   - 修正: 正規イベント系列は1件のまま維持し、日付固有情報を `occurrenceDetails` に分離。静的HTML生成時とブラウザJSON再読込時の双方で日付別表示へ展開するようにした。
   - 9/5: 販売10:10 / 集合13:20 / 開演14:00 / 呼出目安10:00〜11:40。
   - 9/7: 販売12:00 / 集合16:00 / 開演16:30 / 呼出目安11:50〜13:30。
   - 9/14: 詳細未発表として、9/5・9/7の販売・集合・開始・呼出情報を一切継承しない。
   - 修正ファイル: `scripts/special_event_occurrence_details.py`, `scripts/fix_schedule_shell.py`, `scripts/test_special_event_occurrence_details.py`, `.github/workflows/test-schedule-audit.yml`, `.github/workflows/apply-special-event-entities.yml`。
   - PR: #209 `fix: isolate SWEET STEADY release-event details by date`
   - 検証: GitHub Actions `Test schedule audit fixes` run #2 成功。新規回帰テスト、既存正規化テスト、全スケジュール再生成、Node構文チェック、既存帯/UIテスト、9/14実カードの別日情報非混入を確認。

2. [修正済み・検証待ち] P0 Christmas SESSION 12/12 の会場不一致
   - 症状: グループ別・受付別レコードの一部で12/12だけ `venue: null`。合同公式スケジュール行は `有明アリーナ`。表示時の補完で隠れる場合があるが、正規DBに不一致が残っていた。
   - 公式確認: 2026/12/12 Day1は有明アリーナ、OPEN 15:00 / START 17:00。12/13 Day2も有明アリーナ、OPEN 14:00 / START 16:00。
   - 原因: チケット受付・グループ別レコードへ日付と開場/開演は引き継がれている一方、同一物理公演の確定会場が伝播していなかった。合同 `official-schedule` レコードだけが確定会場を保持していた。
   - 修正: `KAWAII LAB. Christmas SESSION 2026` + `2026-12-12` + Day1時刻と整合する行について、合同 `official-schedule` の会場候補が1つに確定する場合のみ、欠損したトップ階層・schedule行のvenueへ伝播する。
   - 安全策: 非空の異なる会場は絶対に上書きせず conflict として停止可能。別イベント・別時刻は対象外。補正済み行に `P0-christmas-session-2026-day1-venue` と公式ソースを記録する。
   - 再発防止: 通常の自動更新が共通で通る `apply_event_scopes.py` に補正を接続。別経路の canonical special-event migration にも補正CLIを接続。
   - 修正ファイル: `scripts/schedule_audit_corrections.py`, `scripts/test_schedule_audit_corrections.py`, `scripts/apply_event_scopes.py`, `.github/workflows/apply-special-event-entities.yml`, `.github/workflows/test-schedule-audit.yml`。
   - 検証予定: 単体4テスト、実データ内の対象トップ階層/schedule行が全て有明アリーナになること、既存全スケジュール生成・Node構文・帯/UIテストをPR CIで確認する。

3. [未着手] P0 SWEET STEADY「お花見会」9/21 の重複・2公演表現不足
   - Zepp Shinjuku / 会場未定が重複。
   - 14:00 / 17:30 の2公演を分離して表現する必要あり。

4. [未着手] P1 同一公演が受付種別ごとに複数カード化
   - CANDY TUNE 10/8仙台ほか。
   - 公演とチケット受付を分離するデータモデルへ寄せる。

5. [未着手] P1 「申込開始開始日時未取得」表示
   - 開始日時欠損時の表示・申込リンク制御を修正。

6. [未着手] P1 終了済み受付に「終了」状態が出ない
   - 現在時刻から受付状態を計算する。

7. [未着手] P1 告知文がイベント名へ混入
   - ニュース見出しからイベント名を正規化する。

8. [未着手] P1 ツアー公演詳細の開場・開演時刻欠落
   - 日ごとの開場・開演を保持・表示する。

9. [未着手] P2 会場詳細ページが「読み込んでいます…」のまま
   - 会場ID化、検索キー正規化、取得失敗時表示を確認。

10. [未着手] P2 「バックアップを表示中。最新データを確認しています…」が残る
    - 最新取得成功後の解除処理、失敗時挙動を確認。

11. [未着手] P2 「182イベント掲載中」の件数定義不一致
    - 公演数と受付レコード数を分離する。

12. [未着手] P2 会場名表記揺れ
    - 正式会場ID・表示名・別名を正規化する。

## 変更履歴
- 2026-09-08: 修正台帳を新規作成。
- 2026-09-08: P0-1 SWEET STEADY 9/5・9/7・9/14 情報混在を修正し、PR #209 のCIで検証完了。
- 2026-09-08: P0-2 Christmas SESSION Day1の正規DB会場欠損の原因を特定。安全な公式会場伝播と共通公開境界への再発防止を実装し、PR CI待ち。
