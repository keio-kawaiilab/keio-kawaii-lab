# スケジュール総点検 修正台帳

最終更新: 2026-09-08
現在の状態: P0-3 本番反映・公開HTML確認まで完了
次の作業対象: P1-4 同一公演が受付種別ごとに複数カード化

## 引き継ぎルール
- 別チャットでは最初にこのファイルを読む。
- 1件ずつ `調査中 → 修正済み → 検証済み → 本番反映確認` の順で進める。
- 修正したファイル名・原因・確認内容を必ず追記する。
- 原則として未検証の変更を `main` に入れない。
- 各項目は、可能なら公式一次情報の確認内容・PR番号・CI結果・本番用データ/HTML反映まで残す。

## 修正対象

1. [本番反映確認済み] P0 SWEET STEADY 9/5・9/7・9/14 リリースイベントの情報混在
   - 原因: 3日分を1つの正規イベント系列に統合したあと、日付固有の `salesStartTime` / `gatheringTime` / `startTime` / `numberedCallTimes` まで親レコードへ残り、表示時に全日へ継承されていた。
   - 修正: 正規イベント系列は1件のまま維持し、日付固有情報を `occurrenceDetails` に分離。静的HTML生成時とブラウザJSON再読込時の双方で日付別表示へ展開するようにした。
   - 9/5: 販売10:10 / 集合13:20 / 開演14:00 / 呼出目安10:00〜11:40。
   - 9/7: 販売12:00 / 集合16:00 / 開演16:30 / 呼出目安11:50〜13:30。
   - 9/14: 詳細未発表として、9/5・9/7の販売・集合・開始・呼出情報を一切継承しない。
   - 修正ファイル: `scripts/special_event_occurrence_details.py`, `scripts/fix_schedule_shell.py`, `scripts/test_special_event_occurrence_details.py`, `.github/workflows/test-schedule-audit.yml`, `.github/workflows/apply-special-event-entities.yml`。
   - PR: #209 `fix: isolate SWEET STEADY release-event details by date`
   - 検証: GitHub Actions `Test schedule audit fixes` run #2 成功。新規回帰テスト、既存正規化テスト、全スケジュール再生成、Node構文チェック、既存帯/UIテスト、9/14実カードの別日情報非混入を確認。

2. [本番反映確認済み] P0 Christmas SESSION 12/12 の会場不一致
   - 症状: グループ別・受付別レコードの一部で12/12だけ `venue: null`。合同公式スケジュール行は `有明アリーナ`。表示時の補完で隠れる場合があるが、正規DBに不一致が残っていた。
   - 公式確認: 2026/12/12 Day1は有明アリーナ、OPEN 15:00 / START 17:00。12/13 Day2も有明アリーナ、OPEN 14:00 / START 16:00。
   - 原因: チケット受付・グループ別レコードへ日付と開場/開演は引き継がれている一方、同一物理公演の確定会場が伝播していなかった。合同 `official-schedule` レコードだけが確定会場を保持していた。
   - 修正: `KAWAII LAB. Christmas SESSION 2026` + `2026-12-12` + Day1時刻と整合する行について、合同 `official-schedule` の会場候補が1つに確定する場合のみ、欠損したトップ階層・schedule行のvenueへ伝播する。
   - 安全策: 非空の異なる会場は絶対に上書きせず conflict として停止可能。別イベント・別時刻は対象外。補正済み行に `P0-christmas-session-2026-day1-venue` と公式ソースを記録する。
   - 再発防止: 通常の自動更新が共通で通る `apply_event_scopes.py` に補正を接続。別経路の canonical special-event migration にも補正CLIを接続。
   - 修正ファイル: `scripts/schedule_audit_corrections.py`, `scripts/test_schedule_audit_corrections.py`, `scripts/apply_event_scopes.py`, `.github/workflows/apply-special-event-entities.yml`, `.github/workflows/test-schedule-audit.yml`。
   - PR: #210 `fix: reconcile Christmas SESSION Day1 venue`
   - 検証: GitHub Actions `Test schedule audit fixes` run #4 成功。単体4テスト、実DBの対象トップ階層/schedule行、全スケジュール再生成、Node構文、既存帯/UIテスト、P0-1回帰テストを確認後、squash merge済み。

3. [本番反映確認済み] P0 SWEET STEADY「お花見会」9/21 の重複・2公演表現不足
   - 症状: 14:00公演が、Zepp Shinjukuを保持する公演レコードと会場未設定のFC受付レコードの2行に分裂。一方で同日17:30の第二回が正規DBに存在しない。
   - 公式確認: 2026/9/21 Zepp Shinjuku (TOKYO)。第一回 OPEN 13:00 / START 14:00、第二回 OPEN 16:30 / START 17:30。
   - 原因: 公式ニュースから「公演」と「FC受付」が別レコード化された一方、同日複数公演を作る取得・正規化処理が第一回しか生成していなかった。
   - 修正: 対象ソース行を、同一公演の受付・取得元メタデータとして統合し、公開境界で物理公演を第一回14:00・第二回17:30のちょうど2行へ正規化する。両公演へ確定会場・開場/開演・公式スケジュールURLを付与する。
   - データ保全: 統合した受付元は `auditMergedTicketOffers`、取得元行は `auditMergedSourceRowIds`、公式根拠は `performanceFactSources` に保持し、重複カードを消しても受付ソース情報は捨てない。
   - 安全策: 対象行にZepp Shinjuku以外の非空会場、または14:00/17:30以外の開始時刻が入った場合は自動上書きせず conflict として公開処理を停止可能。補正は冪等化する。
   - 修正ファイル: `scripts/ohanami_two_show_correction.py`, `scripts/schedule_audit_corrections.py`, `scripts/test_ohanami_two_show_correction.py`, `scripts/test_schedule_audit_corrections.py`, `.github/workflows/apply-special-event-entities.yml`。
   - PR: #211 `fix: split SWEET STEADY Ohanami into two performances`
   - CI検証: GitHub Actions `Test schedule audit fixes` run #5 成功。重複統合、第一回/第二回生成、会場競合停止、既存第二回再利用、冪等性、実DBで14:00/17:30の2行になることに加え、P0-1/P0-2回帰、全スケジュール再生成、Node構文、既存帯/UIテストまで成功。
   - 本番適用改善: PR #212 `ci: run canonical migration after schedule audit corrections` で、監査補正コード変更時に `Apply canonical special-event entities` が自動起動するようにした。
   - 本番反映: PR #212 merge後の `Apply canonical special-event entities` run #4 が成功し、`data/live-events.json` と `schedule.html` を自動再生成・mainへ反映。生成データcommitは `980bc48ab3a337bd3bd81dbd0110849bd13cc287`。
   - 公開HTML確認: `schedule.html` の静的カードは `単独公演 お花見会 第一回` と `単独公演 お花見会 第二回` の2枚だけになり、両方Zepp Shinjuku。正規DBも第一回 OPEN13:00/START14:00、第二回 OPEN16:30/START17:30 の2行を保持し、旧FC受付行は独立カードではなく統合メタデータへ移行済み。
   - デプロイ: 上記生成データcommitに対する GitHub Pages `pages build and deployment` run #2799 が成功。P0-3は公開反映まで完了。

4. [次の作業] P1 同一公演が受付種別ごとに複数カード化
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
- 2026-09-08: P0-2 Christmas SESSION Day1をPR #210のCI run #4で検証し、mainへsquash merge。P0-3へ移行。
- 2026-09-08: P0-3 SWEET STEADY「お花見会」は第一回の重複と第二回欠落を修正。PR #211のCI run #5で新規回帰・実DB・既存P0回帰・全生成/UIテストまで検証完了。
- 2026-09-08: PR #212で監査補正変更時のcanonical migration自動起動を追加。migration run #4で正規DB/公開HTMLへ適用し、Pages run #2799成功まで確認。P0-3を本番反映確認済みに確定し、次をP1-4とした。
