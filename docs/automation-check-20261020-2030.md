# 2026-10-20 SWEET STEADYオンライン特典会の受付統合

## 根拠（日本時間で再確認）

- https://sukisuki-shop.com/goods/6500000004624
  - 2026年10月23日15:00配信、7名、ちょーだいHAPPY！MV衣装。
  - 抽選申込10月13日15:00〜14日23:59、当落15日中、入金17日23:59。
- https://sukisuki-shop.com/goods/6500000004625
  - 同じ10月23日15:00配信・7名・衣装の二次抽選販売。
  - 抽選申込10月18日15:00〜19日23:59、当落20日中、入金21日23:59。

元データ/publicEventsでは2行だった。ブラウザ側の表示上の重複抑制に依存せず、既存の正規化処理で1公演と2受付に統合する。どちらも受付は終了しているが、二次受付の入金期限は翌日なので、期限を消さず受付子要素に保持する。元IDはsourceRowIds/sourceRowIdで保存する。別日・別時刻・別グループ・別商品には適用しない。再取得で元の2行が戻っても、正規化時に同じ公演へ統合する。

## 確認範囲

合同と5グループの公開トップ、NEWS、10月SCHEDULEを開いた。CANDYトップはこの確認環境でタイムアウトしたが、NEWSとSCHEDULEは読めたため全体停止にはしない。CUTIE 92733、FRUITS ZIPPER 92554、SWEET STEADY/合同92282の今夜23:59締切を原文確認し、正規の申込リンクも開いた（FC受付はログイン画面まで）。CANDY 4623は販売終了、開催日は今日17:00。SWEET 4625は当落20日・入金21日・開催23日を区別した。

最新統合更新39411845417とPages39412588509は成功。公開前監査status: ok/errorCount: 0、discovery-publication-healthはmissingOffers/sourceFailuresなし、個別保留7件。未確定の項目は他の正常情報と混同しない。前回のCUTIEアップグレード訂正、CANDY先着先行とリセールの区別、本日CANDYオン特1公演も公開画面で維持を確認した。

## 検証

## 再収集後に確認した同一公演の追加統合

https://sweetsteady.asobisystem.com/news/detail/91244 の本文は11月16日Zepp Haneda(TOKYO)、開場17:30/開演18:30の1公演、FC受付9月29日18:00〜10月4日23:59を明記。再収集で公演の日程行と終了済み受付行が別publicEventsとして残ったため、この公式記事・日付・時刻に限定して1公演へ統合する。外部出演の区分は変えず、終了済みFC受付はoffersと元IDで保持する。他の記事・日付・開演時刻を同一視しない。既存の別商品・別特典会への一般化もしない。

純Python回帰テスト80件成功。受付2件の当落・入金期限、親公演への受付項目の流出防止、冪等性、元行の再取得、別日時等の除外、外部出演の受付履歴保持を追加。最新本番データへ適用した監査もエラー0・隔離0だった。画面生成、インラインJavaScript構文、申込帯・主催フィルタ・プリセール判定/キャッシュ更新経路のNodeテストも成功。

## 公開完了確認（20:43 日本時間）

- ソース修正: 0afefaa（10月23日オン特）、4edb6a2（11月16日外部出演）。
- 本文収集・監査・公開 https://github.com/keio-kawaiilab/keio-kawaii-lab/actions/runs/39415443685 成功。次の統合巡回 https://github.com/keio-kawaiilab/keio-kawaii-lab/actions/runs/39415443961 も全取得元・統合公開・情報源監視まで成功。再取得後も両方の統合が維持された。
- 最新main 121a2df の publicEvents と live-runtime-fallback.js の両方で、10月23日はknown-sweet-steady-online-20261023が1件/2受付、11月16日はknown-sweet-ebichu-20261116が1件/1受付。元IDはそれぞれ2個ずつ保持。
- Pages https://github.com/keio-kawaiilab/keio-kawaii-lab/actions/runs/39416745255 成功。live.htmlから実際に開き直した公開画面の更新日時は20:41:21。10月23日15:00オン特が1件、当落と入金期限マークが各1個。CANDY本日17:00オン特も1件で終了した販売への有効な申込導線なし。
- 外部出演を含めるフィルタで11月16日を1件と確認。Zepp Haneda(TOKYO)、開場17:30/開演18:30、終了した9月29日18:00〜10月4日23:59のFC受付履歴を保持。主催のみの既定表示へ戻した。
- 最新監査はstatus: ok/errorCount: 0。発見・公開照合はmissingOffers/sourceFailuresなし、failureCount: 0。既存の個別保留7件は保持し、問題のない更新を公開した。
