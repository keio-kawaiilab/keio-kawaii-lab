# スケジュール総点検 修正台帳

最終更新: 2026-09-08
現在の状態: 緊急修正 10/12・10/17 外部主催判定／10/12同一イベント重複 本番反映確認まで完了
次の作業対象: P2-11 「182イベント掲載中」の件数定義不一致

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

4. [本番反映確認済み] P1 同一公演が受付種別ごとに複数カード化
   - 代表症状: CANDY TUNE 2026/10/8 仙台サンプラザホール 18:30公演が、FC先行・イープラス一般発売・ローチケ由来・公式ツアー日程など複数の取得行として存在し、正規DBと静的HTMLで受付ごとの独立カードになり得た。
   - 原因: 収集DBの1行が「物理公演」と「チケット受付」の両方を兼ねていた。ブラウザ実行後の `performanceModels()` には公演単位の束ね処理があったが、公開JSONと初期静的HTMLには同等の公演エンティティ層がなかった。
   - 修正: 収集元の `events` は証跡・更新互換性のため削除せず保持し、公開用 `publicEvents` を新設。KAWAII LAB.主催の通常ライブは `group + date + verified start time` を物理公演キーとして1公演1エンティティ化し、FC/ぴあ/ローチケ/e+/公式などの受付を `offers` 配列へ格納する。
   - データ保全: 元取得行IDを `sourceRowIds`、受付元を `offers[].sourceRowId`、URL群を各offerと公演側へ残す。マルチデイツアーの元レコードは公開モデルだけ日付ごとの物理公演へ展開し、収集用 `events` 自体は変更しない。
   - 静的HTML: `publicEvents` 由来でカードを生成し、1公演カード内に受付ごとのチケット欄を表示する。ブラウザ再読込も `data.publicEvents || data.events` を優先し、performance entityの `offers` を既存UIへ展開する。
   - 自動更新: 全公開経路が最後に通る `strip_schedule_explanations.py` から公開モデル生成を必須実行。15分ごとの分散自動更新・旧緊急更新・canonical migrationのいずれでも公開モデル生成を回避できない。
   - 修正ファイル: `scripts/performance_entities.py`, `scripts/install_performance_public_view.py`, `scripts/test_performance_entities.py`, `scripts/strip_schedule_explanations.py`, `.github/workflows/test-schedule-audit.yml`, `.github/workflows/apply-special-event-entities.yml`。
   - PR: #213 `fix: model one performance with multiple ticket offers`
   - CI検証: GitHub Actions `Test schedule audit fixes` run #6 成功。新規performance entity単体/実DBテスト、P0回帰、全スケジュール再生成、Node構文、既存帯/UIテスト、静的HTMLで10/8仙台が1枚かつFC/一般発売を同カード内に保持することを確認。
   - 初回本番migration: `Apply canonical special-event entities` run #5 はテスト・公開モデル生成・再構築まで成功したが、同時刻の15分自動更新がmainを進めたため生成済み `data/live-events.json` / `schedule.html` のrebaseが競合し、最新データを上書きせず安全に停止した。
   - 競合再発防止: PR #214 `ci: rebuild canonical schedule after concurrent refresh` で、push競合時は生成済みファイルをrebaseせず最新mainへ戻り、最新の収集データ上で正規化・監査補正・全スケジュール生成・performance公開モデル生成・Node/UIテストを最初からやり直してからpushする方式へ変更。PR #214の `Test schedule audit fixes` run #7 成功。
   - 本番反映: #214 merge後の `Apply canonical special-event entities` run #6 が最終commitまで成功。最新mainを基礎に生成した公開データcommitは `f871af9593c71b0fc47d90a1e03234b04881d215`。
   - 正規公開JSON確認: `publicEvents` 内のCANDY TUNE 10/8仙台は `performance-CANDY-TUNE-2026-10-08-time-18-30` の1公演のみ。会場=宮城県 仙台サンプラザホール、OPEN17:30/START18:30。`offers` にFC先行とイープラス一般発売を保持し、ローチケ等の元取得行も `sourceRowIds` で追跡可能。
   - 公開HTML確認: `schedule.html` のCANDY TUNE 10/8仙台ツアーカードは1枚だけで、同カード内のチケット欄に「公式 / FC：FC先行」と「イープラス：先着 ★一般発売」を表示。最新JSON再読込時も `publicEvents` を優先するため、受付別独立カードへ戻らない。
   - デプロイ: 生成データcommit `f871af9593c71b0fc47d90a1e03234b04881d215` に対する GitHub Pages `pages build and deployment` run #2805（run ID 34184502227）が成功。P1-4は公開反映まで完了。

5. [本番反映確認済み] P1 「申込開始開始日時未取得」表示
   - 症状: 受付開始日時が欠損した行で、静的カードは項目名「申込開始」と値「開始日時未取得」が連結され `申込開始開始日時未取得` と表示され得た。ブラウザ再描画側も開始日時不明を期間先頭へそのまま入れ、かつ締切が未来なら `受付中・予定` と判定して `申込ページ →` を表示していた。
   - 原因: 静的HTML生成とブラウザJSで欠損表現が別実装になっており、`applyStart` 欠損を「不明な事実」ではなくカレンダー帯生成用のsynthetic開始日と混同していた。URLの存在だけでも申込CTAを有効化していた。
   - 修正: 開始日時欠損時は表示値を `日時未取得` に統一。受付欄では `申込開始：日時未取得` とし、締切だけ取得済みなら `／ 締切 YYYY/M/D HH:MM` を併記する。開始日時が確認できない受付は `受付中・予定` にせず状態を `開始日時未取得` とする。
   - リンク制御: 公式・プレイガイドURL自体は証跡として保持するが、開始日時不明時は申込可能と断定するCTAを出さず、`受付詳細を確認 →` のdetail-onlyリンクへ降格。開始日時が取得済みの受付は従来どおり申込先リンクを維持する。
   - 再発防止: `strip_schedule_explanations.py` を公開境界ラッパー化し、既存のcanonical公開モデル生成・最終更新時刻反映後に `fix_missing_application_start_ui.py` を必ず通す。静的カードと実際に配信されるインラインJSの双方を同じ最終境界で検査・補正し、`/tmp/schedule-inline.js` も補正後に書き直してCIのNode構文検査対象にする。
   - 修正ファイル: `scripts/fix_missing_application_start_ui.py`, `scripts/strip_schedule_explanations.py`, `scripts/strip_schedule_explanations_core.py`, `scripts/test_schedule_scope_ui.js`。
   - PR: #215 `fix: handle unknown application start times safely`
   - CI検証: 初回run #10は新実装自体の公開再生成・Node構文・既存Python回帰まで成功したが、旧UIテストが `open=!end||end>=now` の固定文字列を期待して停止。テストを新仕様 `open=!missingStart&&(!end||end>=now)` と、欠損時の状態・detail-only CTA・重複文言禁止まで確認する形へ更新。`Test schedule audit fixes` run #11（run ID 34185322550）は全工程成功し、P0/P1-4回帰・全再生成・Node/UIテストも通過。
   - 本番反映: PR #215 merge後の `Apply canonical special-event entities` run #7（run ID 34185358225）が、最新main上でcanonical検証・公開データ/HTML再生成・mainへのcommitまで成功。生成公開commitは `53f75c83aab4f15a31661098e84e78f4487deca6`。
   - 公開HTML確認: mainの `schedule.html` で `申込開始開始日時未取得` は0件。実例としてCANDY TUNE 10/1生誕祭の開始日時不明アップグレード、CANDY TUNEツアーの開始日時不明ぴあ受付は `申込開始：日時未取得` と表示され、リンクは `data-action-mode="detail"` の `受付詳細を確認 →` になった。ブラウザruntimeも開始日時不明をopen扱いしない。
   - デプロイ: 生成公開commit `53f75c83aab4f15a31661098e84e78f4487deca6` に対する GitHub Pages `pages build and deployment` run #2810（run ID 34185373763）が成功。P1-5は公開反映まで完了。

6. [本番反映確認済み] P1 終了済み受付に「終了」状態が出ない
   - 症状: 公開用performanceカードの静的HTMLには受付状態表示がなく、ブラウザ再描画側も開始日時欠損を優先すると、締切が既に過ぎていても `開始日時未取得` のままになり得た。また開始前と受付中の区別もなかった。
   - 原因: 静的チケット欄とruntimeの受付状態判定が別実装で、runtimeは締切の単純比較だけ、静的HTMLは状態計算なしだった。
   - 修正: JSTの現在時刻に対して受付開始・締切を比較し、`受付予定` / `受付中` / `受付終了` / `開始日時未取得` の4状態へ統一。確定した締切が過ぎている場合は開始日時不明より強い事実として `受付終了` を優先する。
   - リンク制御: `受付終了` と `開始日時未取得` は申込可能と誤認させない `受付詳細を確認 →` のdetail-onlyリンクへ変更。`受付予定` と `受付中` は申込先・商品/整理券ページへのリンクを維持する。
   - 静的/動的整合: 最終公開境界 `fix_missing_application_start_ui.py` で静的performanceカードにも同じ状態を付与し、ブラウザ `offerHtml()` も同じ時刻条件で再計算する。既存の当日締切時刻比較も維持する。
   - 再発防止: `test_schedule_scope_ui.js` に4状態、終了済み静的カード、detail-only、当日締切比較の検査を追加。`fix_missing_application_start_ui.py` / UIテスト変更時にもcanonical migrationが自動起動するようworkflow対象を追加。
   - 修正ファイル: `scripts/fix_missing_application_start_ui.py`, `scripts/test_schedule_scope_ui.js`, `.github/workflows/apply-special-event-entities.yml`。
   - PR: #217 `fix: show time-aware ticket reception states`
   - CI検証: GitHub Actions `Test schedule audit fixes` run #12（run ID 34192269809）が全工程成功。既存P0/P1回帰、全スケジュール再生成、Node構文、帯/UI、CANDY TUNE仙台1公演化、Christmas SESSION、SWEET STEPの日付別表示まで通過。
   - 本番反映: PR #217 merge後の `Apply canonical special-event entities` run #8（run ID 34192312850）が、最新mainからcanonical検証・公開HTML再生成・commitまで成功。生成公開commitは `668e1632920f1d325eb39d0b85a9dc6d64bd203d`。
   - 公開HTML確認: CANDY TUNE 9/9大阪のFC先行・ぴあ2次は `受付終了` + `data-action-mode="detail"` の `受付詳細を確認 →`。FRUITS ZIPPER 9/16以降の将来リセールは `受付予定`、現在期間内の受付は `受付中` と表示。browser runtimeも同じ4状態を現在時刻から計算する。
   - デプロイ: 生成公開commit `668e1632920f1d325eb39d0b85a9dc6d64bd203d` に対する GitHub Pages `pages build and deployment` run #2816（run ID 34192333184）が成功。P1-6は公開反映まで完了。

7. [本番反映確認済み] P1 告知文がイベント名へ混入
   - 症状: MORE STAR 2026/10/17 Zepp Namba公演などで、公式ニュースの見出し `2026.09.07 2026年10月17日(土) ... 出演決定！MORE STAR FC会員先行受付開始` がそのまま公開イベント名へ採用されていた。
   - 原因: `performance_entities.py` が同一物理公演の元レコードから信頼度の高いbase行を選び、その行の `title` も丸ごと継承していた。公式ニュース行は高優先度なので、別ソースに短い正式イベント名があっても告知見出しが勝つ場合があった。
   - 修正: 最終公開境界に `normalize_public_event_titles.py` を追加。現在の公開タイトルが「出演決定」「受付開始」などの告知文らしい場合に限り、同じ物理公演の `sourceRowIds` 内に既存する告知語なしの候補を探す。さらに、その候補の正規化文字列が長い告知見出し内に実際に含まれる場合だけ、その既存候補へ差し替える。文字列を推測生成したり、正規表現で無理に切り出したりはしない。
   - データ保全: 収集用 `events` の元ニュース見出しは証跡として一切書き換えない。公開側だけ `title` / `eventTitle` / `displayTitle` をそろえ、`publicTitleOriginal` / `publicTitleSourceRowId` / `publicTitleNormalization` に変更前タイトルと採用根拠を保持する。
   - 静的/動的整合: `publicEvents` だけでなく、`schedule.html` の静的カードと `snapshot-data` も最終公開境界で同じ正式名へそろえる。既存の公開処理が必ず通る `strip_schedule_explanations.py` から正規化を呼ぶため、自動更新経路でも回避できない。
   - 実例確認: MORE STAR 2026/10/17は `FM大阪 『Live or Treat 2026』 in Zepp Namba` に正規化。元の公式ニュース取得行 `f054f2a8893de7de` には `FC会員先行受付開始` を含む原見出しをそのまま保持。
   - 修正ファイル: `scripts/normalize_public_event_titles.py`, `scripts/strip_schedule_explanations.py`。
   - PR: #218 `fix: normalize announcement-style event titles`
   - CI検証: GitHub Actions `Test schedule audit fixes` run #13（run ID 34198288275）が全工程成功。正規化対象は `performance-MORE-STAR-2026-10-17-time-16-30` の1件だけで、既存P0/P1回帰・全スケジュール再生成・Node/UI検査も通過。公開正式名への変更とraw取得行温存を同時に検査した。
   - 本番反映: PR #218 merge後の `Apply canonical special-event entities` run #9（run ID 34198368420）が、最新mainから全再生成・検証・commitまで成功。生成公開commitは `093c4694f46b3098236efaa23e63c3109d875940`。
   - 公開HTML確認: 上記生成commitの `data/live-events.json` と `schedule.html` で、MORE STAR 10/17の公開タイトルが `FM大阪 『Live or Treat 2026』 in Zepp Namba` になり、長い告知見出しを公開カード名として使用しないことを確認。
   - デプロイ: 生成公開commit `093c4694f46b3098236efaa23e63c3109d875940` に対する GitHub Pages `pages build and deployment` run #2822（run ID 34198394969）が成功。P1-7は公開反映まで完了。

8. [本番反映確認済み] P1 ツアー公演詳細の開場・開演時刻欠落
   - 症状: 公開用performanceモデルに日別OPEN/STARTが存在していても、初期静的HTMLのperformanceカードは「開催日」だけを描画して開場・開演を表示していなかった。またbrowser runtimeで旧multi-day tour行を公式scheduleから補完する際、受付行のトップ階層時刻が日別公式時刻より優先される経路があった。
   - 原因: `build_schedule_snapshot.build_card()` のライブカードは日付のみで時刻を描画せず、runtime `repair()` は `x.openTime || r.openTime` / `x.startTime || r.startTime` の順で補完していた。
   - 修正: `install_performance_public_view.py` の最終公開境界でperformance静的カードを `開催日時` 表示へ差し替え、`eventDate + openTime + startTime` を描画。runtime repairも `r.openTime || x.openTime` / `r.startTime || x.startTime` に変更し、日別公式schedule occurrenceを優先するよう統一した。
   - 安全策・回帰: 時刻の異なるCANDY TUNEツアー2公演を実DBで固定検査。2026/10/4 函館市民会館はOPEN16:30/START17:30、2026/10/8 仙台サンプラザホールはOPEN17:30/START18:30。両方を同時に検査することで、ツアー代表時刻を全日に誤伝播する再発も防ぐ。仙台のFC先行/一般発売の複数受付保持も継続確認する。
   - 修正ファイル: `scripts/install_performance_public_view.py`。
   - PR: #219 `fix: preserve per-day tour performance times`
   - CI検証: GitHub Actions `Test schedule audit fixes` run #14（run ID 34199949029）が全工程成功。新規ツアー時刻ガード、実DB再生成、既存P0/P1回帰、Node構文、帯/UI、仙台複数受付、Christmas SESSION、SWEET STEP日別表示まで通過。
   - 本番反映: PR #219 merge後の `Apply canonical special-event entities` run #10（run ID 34200007528）が成功。生成公開commitは `d441842e109b78b07402c0215e1b49f273a2500f`。
   - 公開HTML確認: 生成commitの `schedule.html` で、函館は `2026/10/4 ／ 開場 16:30 ／ 開演 17:30`、仙台は `2026/10/8 ／ 開場 17:30 ／ 開演 18:30` を初期静的カードから表示。browser runtimeも日別公式時刻優先へ統一されていることを確認。
   - デプロイ: 生成公開commit `d441842e109b78b07402c0215e1b49f273a2500f` に対する GitHub Pages `pages build and deployment` run #2826（run ID 34200033161）が成功。P1-8は公開反映まで完了。

9. [本番反映確認済み] P2 会場詳細ページが「読み込んでいます…」のまま
   - 監査再確認: 元監査は実ブラウザでJavaScript実行後を確認できず、初期HTMLの `会場情報を読み込んでいます…` placeholderだけを見て不具合扱いしていた。現行本番では東京ガーデンシアター詳細が会場名・住所・アクセス・収容人数・今後の公演まで正常表示されることを再確認した。
   - 既存実装: `data/venues.json` はstableな会場 `id` を保持。一覧の詳細リンクは `venue.html?id=...` を優先し、`venue-detail.js` は `?id=` の完全一致を第一候補にする。旧 `?name=` は会場名・aliasesを正規化して完全一致するフォールバックとして維持する。
   - 取得失敗時: 会場JSON等の取得が失敗した場合はloading placeholderを残さず、`会場情報を読み込めませんでした。` と会場一覧へのリンクへ置換する既存処理を確認。`venue-detail.js` / `venue-detail-cleanup.js` もversion query付きで読み込み、古い壊れたJSキャッシュを避ける。
   - 既修正確認: 2026/8/25の既存履歴に、cleanup observer loop修正、会場詳細JS構文CI、detail scriptのcache bustがすでに入っていることを確認。したがって今回は正常な本番描画ロジックを無理に変更しない。
   - 再発防止: `scripts/test_venue_detail_contract.js` を追加し、全会場のID存在・一意性、ID-first詳細リンク、ID解決、name/alias正規化フォールバック、取得失敗表示、detail scriptのcache bustを契約テスト化。`.github/workflows/check-venue-detail.yml` の監視pathも `venue.html` / `venues.js` / `data/venues.json` / 新テストまで拡張した。
   - 修正ファイル: `scripts/test_venue_detail_contract.js`, `.github/workflows/check-venue-detail.yml`。
   - PR: #220 `test: guard venue detail loading behavior`
   - CI検証: PR上の `Check venue detail JavaScript` run #3（run ID 34202434645）成功。新規 `Check venue detail loading contract` も成功。併せて `Test schedule audit fixes` run #15（run ID 34202434693）も全工程成功し、既存P0/P1回帰を壊していないことを確認。main反映後の会場専用run #4（run ID 34202501405）も成功。
   - 本番反映: PR #220をsquash mergeし、main commit `4a086fdd41841f884f17b87e882c749e1dda958a` へ反映。
   - デプロイ: 上記main commitに対する GitHub Pages `pages build and deployment` run #2828（run ID 34202500419）が成功。
   - 判定: 現在の本番不具合ではなく元監査の誤検知。ただし同症状の再発条件をCIで固定し、本番正常表示・main上CI・Pages成功まで確認してP2-9を完了とした。

10. [本番反映確認済み] P2 「バックアップを表示中。最新データを確認しています…」が残る
    - 症状: 初期HTMLは自動生成済みバックアップを即時表示し、`data/live-events.json` の最新取得中は `バックアップを表示中。最新データを確認しています…` と表示。通常の成功・失敗では状態遷移するが、通信リクエストがpendingのまま完了しない場合は初期文言が残り続ける余地があった。
    - 原因: runtimeの最新JSON取得が素の `fetch(..., {cache:'no-store'})` で、成功時・catch時の終了表示は実装済みだった一方、取得自体に上限時間がなかった。
    - 修正: `fetchLatestScheduleData(url, timeoutMs)` を公開runtimeへ導入し、最新JSON確認を10秒で打ち切る。10秒以内に成功すれば `最終更新: ...` へ更新し最新JSONで再描画、エラーまたはタイムアウトなら生成済みバックアップを維持して `最新JSONの読込に失敗したため、自動生成済みバックアップを表示しています。` へ確定する。
    - 自動更新耐性: `guard_schedule_latest_data_loading.py` を追加し、全公開経路が通る `strip_schedule_explanations.py` の最終境界から必ず適用。単発のHTML手修正ではなく、今後の自動再生成でも無制限fetchへ戻らない。
    - 再発防止: `test_schedule_scope_ui.js` で初期checking表示、10秒ガード、旧無制限fetch消滅、成功時終了表示、失敗/タイムアウト時終了表示を契約検査。
    - 修正ファイル: `scripts/guard_schedule_latest_data_loading.py`, `scripts/strip_schedule_explanations.py`, `scripts/test_schedule_scope_ui.js`。
    - PR: #223 `fix: bound schedule latest-data loading`
    - CI検証: 初回 `Test schedule audit fixes` run #16（run ID 34233399768）は新ガード自体の適用後、既存Node疑似ブラウザが `clearTimeout` を提供していないため停止。既存監査単体は全成功。ガードを `settled` フラグだけで安全に終端する形へ調整し、run #17（run ID 34233583164）は全工程成功。公開再生成、Node/UI、仙台複数受付、Christmas SESSION、SWEET STEP等の既存回帰まで通過。
    - 本番反映: PR #223をsquash merge。main commit `fc7e6311803785e565e6a9394218ef659455bd07`。続く `Apply canonical special-event entities` run #11（run ID 34233692474）が最新main上で公開HTML再生成・検証・commitまで成功。生成公開commitは `bd3c89ab54bab9c8ded5678448287fb68ed46ced`。
    - 公開HTML確認: 生成commitの `schedule.html` に `fetchLatestScheduleData('./data/live-events.json?ts='+Date.now(),10000)` が存在し、成功時 `最終更新: ...` / 失敗・タイムアウト時バックアップ確定の両終了経路を保持。
    - デプロイ: 生成公開commitに対する GitHub Pages `pages build and deployment` run #2838（run ID 34233726186）がbuild/deployとも成功。P2-10は公開反映まで完了。

10-A. [本番反映確認済み] P1 外部主催イベントの主催誤判定・10/12同一イベント7重複
    - 症状: 2026/10/12 `KAWAII LAB. COLLECTION produced by TGC ～KAWAIIっちゃ in KITAKYUSHU～` が、同じ北九州メッセ・OPEN14:00/START16:00の物理イベントにもかかわらず、CANDY TUNE / CUTIE STREET / FRUITS ZIPPER / KAWAII LAB. SOUTH / KAWAII LAB.合同 / MORE STAR / SWEET STEADY の7カードに分裂していた。2026/10/17 MORE STAR `FM大阪 『Live or Treat 2026』 in Zepp Namba` も `KAWAII LAB.主催のみ` 側へ誤分類されていた。
    - 公式確認: 10/12のTGC公式ページは主催を `KAWAII LAB. COLLECTION実行委員会`、企画・制作を `株式会社W TOKYO` と明記。10/17のMORE STAR公式告知は `主催：FM大阪` と明記。サイトの `KAWAII LAB.主催のみ` 定義では両方とも外部出演として扱う。
    - 原因: `schedule_scope.py` のタイトルヒューリスティックが `KAWAII LAB. COLLECTION` を先に主催扱いし、`produced by TGC` を含む外部主催情報より優先していた。また既存の公開performance統合は基本的に主催イベントを対象にしており、グループ別に取得された同一外部イベントを横断して1物理イベントへ束ねる最終境界がなかった。
    - 修正: `normalize_external_event_public_view.py` を追加。公式主催者を確認済みの2イベント系列を最終公開境界で `eventScope=external` に固定し、取得元raw行は証跡として保持したまま公開用行だけ同一物理イベントへ統合する。10/12は公開1イベントに集約し、出演6組 `FRUITS ZIPPER / CANDY TUNE / SWEET STEADY / CUTIE STREET / MORE STAR / KAWAII LAB. SOUTH` を `participants` に保持。10/17も複数受付・複数取得元を1イベント内へ束ねる。
    - 主催のみ表示: `schedule.html` の初期静的カードも補正後snapshotから再生成し、10/12・10/17を `KAWAII LAB.主催のみ` から除外。`participants` は既存グループフィルタが参照するため、外部出演を含む表示では10/12を各出演グループから検索可能なまま維持する。
    - 再発防止: `strip_schedule_explanations.py` から外部イベント補正を必須実行。`test_schedule_scope_ui.js` で10/12=公開1件・external・出演6組、10/17=公開1件・external、両イベントが主催のみ静的カードへ漏れないことを固定検査する。
    - 修正ファイル: `scripts/normalize_external_event_public_view.py`, `scripts/strip_schedule_explanations.py`, `scripts/test_schedule_scope_ui.js`。
    - PR: #224 `fix: classify verified external events and dedupe Kawacolle`
    - CI検証: `Test schedule audit fixes` run #18（run ID 34236260359）が全工程成功。今回の10/12・10/17契約検査に加え、既存の仙台複数受付、Christmas SESSION、SWEET STEP、Node/UI等の全回帰を通過。
    - 本番反映: PR #224をsquash merge（main merge commit `1f7f1186ff8fdc852bcaae9a15d30e147abc502d`）。続く `Apply canonical special-event entities` run #12（run ID 34236359700）が公開JSON/HTML再生成・検証・main commitまで成功。生成公開commitは `9292c390a4affe5ae26dfe513266f244def7724b`。
    - 公開データ確認: 生成DBの該当raw取得行は `eventScope=external`、`eventScopeSource=verified-organizer`、主催者根拠を保持。公開モデルはCIで10/12を1件・10/17を1件に固定検証済み。
    - デプロイ: 生成公開commitに対する GitHub Pages `pages build and deployment` run #2843（run ID 34236399741）が成功。緊急修正は公開反映まで完了。

11. [次の作業] P2 「182イベント掲載中」の件数定義不一致
    - 公演数と受付レコード数を分離する。

12. [未着手] P2 会場名表記揺れ
    - 正式会場ID・表示名・別名を正規化する。

## 変更履歴
- 2026-09-08: 修正台帳を新規作成。
- 2026-09-08: P0-1 SWEET STEADY 9/5・9/7・9/14 情報混在を修正し、PR #209 のCIで検証完了。
- 2026-09-08: P0-2 Christmas SESSION Day1をPR #210のCI run #4で検証し、mainへsquash merge。P0-3へ移行。
- 2026-09-08: P0-3 SWEET STEADY「お花見会」は第一回の重複と第二回欠落を修正。PR #211のCI run #5で新規回帰・実DB・既存P0回帰・全生成/UIテストまで検証完了。
- 2026-09-08: PR #212で監査補正変更時のcanonical migration自動起動を追加。migration run #4で正規DB/公開HTMLへ適用し、Pages run #2799成功まで確認。P0-3を本番反映確認済みに確定し、次をP1-4とした。
- 2026-09-08: P1-4は収集用eventsを温存しつつ公開用`publicEvents`を導入。PR #213のCI run #6で10/8仙台1公演＋複数受付、既存P0回帰、全生成/UIテストを検証。
- 2026-09-08: #213本番migration時に15分自動更新とのmain競合を検出。最新データを上書きせず停止したうえ、PR #214で「競合時は最新mainから全再生成」へ変更。#214 CI run #7成功。
- 2026-09-08: #214後のcanonical migration run #6が最新データ上の再生成・commitまで成功。commit `f871af9593c71b0fc47d90a1e03234b04881d215` の公開JSON/静的HTMLを確認し、Pages run #2805成功まで確認。P1-4を本番反映確認済みに確定し、次をP1-5とした。
- 2026-09-08: P1-5の開始日時欠損表示・CTAをPR #215で修正。CI run #11、canonical migration run #7、生成commit `53f75c83aab4f15a31661098e84e78f4487deca6`、Pages run #2810の成功と公開HTMLを確認。P1-5を本番反映確認済みに確定し、次をP1-6とした。
- 2026-09-08: P1-6の受付状態をPR #217で現在時刻ベースの4状態へ統一。CI run #12、canonical migration run #8、生成commit `668e1632920f1d325eb39d0b85a9dc6d64bd203d`、Pages run #2816の成功と静的/runtime双方の公開HTMLを確認。P1-6を本番反映確認済みに確定し、次をP1-7とした。
- 2026-09-08: P1-7の告知文混入をPR #218で、同一物理公演の別ソースに実在する正式タイトルだけを採用する方式へ修正。CI run #13、canonical migration run #9、生成commit `093c4694f46b3098236efaa23e63c3109d875940`、Pages run #2822の成功とMORE STAR 10/17公開カードを確認。rawニュース見出しも証跡として温存し、P1-7を本番反映確認済みに確定。次をP1-8とした。
- 2026-09-08: P1-8はPR #219でツアー日別OPEN/STARTの静的表示とruntime補完優先順位を修正。CI run #14、canonical migration run #10、生成commit `d441842e109b78b07402c0215e1b49f273a2500f`、Pages run #2826（run ID 34200033161）の成功と公開HTMLを確認。P1-8を本番反映確認済みに確定し、次をP2-9とした。
- 2026-09-08: P2-9は元監査がJavaScript実行前のplaceholderだけを見た誤検知と判明。現行本番の東京ガーデンシアター詳細が正常表示し、既存のstable venue ID・name/alias正規化・取得失敗表示・cache bustを確認。PR #220で回帰契約テストを追加し、venue CI run #3、schedule audit run #15、main venue CI run #4、Pages run #2828成功まで確認。P2-9を本番反映確認済みに確定し、次をP2-10とした。
- 2026-09-08: P2-10は最新JSON取得にタイムアウトがなくpending時にchecking表示が残り得ることを特定。PR #223で10秒のbounded fetchを最終公開境界へ導入し、CI run #17、canonical migration run #11、生成commit `bd3c89ab54bab9c8ded5678448287fb68ed46ced`、Pages run #2838成功と公開HTMLへの10秒ガード反映まで確認。P2-10を本番反映確認済みに確定し、次をP2-11とした。
- 2026-09-08: 10/12 Kawacolleが同一物理イベントなのに7カードへ分裂し、10/12・10/17が主催のみへ誤分類される問題を緊急修正。PR #224で公式主催者根拠によるexternal固定＋外部イベント系列の公開1件化を最終公開境界へ追加。CI run #18、canonical migration run #12、生成commit `9292c390a4affe5ae26dfe513266f244def7724b`、Pages run #2843成功まで確認。次の通常作業対象はP2-11のまま。