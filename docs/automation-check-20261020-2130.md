# 2026-10-20 21時台 公式照合・重複受付修正

公式本文 https://kawaiilab.asobisystem.com/news/detail/92282 と受付リンク（FCログイン入口まで）を確認。12/8 白石まゆみ生誕祭 19:00、10/14 12:00–10/20 23:59は KAWAII LAB. FC有料会員向けの1受付。recent-official-bodyのFC先行行とcentral collector行が同じ記事・期間を2本表示していた。

記事・グループ・開催日・開演・受付期間が全て一致する場合のみ区分を正規化。新規収集と既存正規データの双方に適用。過去のグループFC受付（公式90613、9/29–10/6）は変更しない。履歴はID・初回観測・受付期間を保存し、誤区分の旧観測だけ再表示対象から外す。

ローカル関連83回帰テスト成功。本文再取得Actions 39421713275成功（27テスト）、Ticket flow release check 39421713110成功。通常統合更新39421713153成功、公開前監査21:31:36 status=ok/errorCount=0。

6系統公式NEWS・SCHEDULEを再読、公開トップを確認（CUTIEトップのみ取得タイムアウト、NEWS/SCHEDULE/本文は読めた）。SUKISUKI4623は本日17:00販売終了、CANDY本日公演1件保持。SWEET4624/4625は10/23 15:00同公演の別受付、当落/入金日を区別。21:03公開データで両統合の再発なし。今夜締切CUTIE92733・FZ92554・中央FC92282を再確認。公式discovery20:57取得失敗0、公開漏れ0・保留7。ローチケは部分取得タイムアウトで前回値保持、全体公開停止なし。

## 公開検証

- 修正ソース commit 265f24fa63be121eefa95c7be9f60fa8c23ef897、本文反映6196bdc1514a1f79f96d9595d6059ba0d2c8f4a3、通常統合bd4974aa55ff62d967f363929780c72364f8ed91、公開ガードe9ed81fe40fb273dcf294fa18216ce7112c04019。
- Pages 39423100855 success後、通常schedule.htmlを再読。白石公演カード1件、申込帯1本。履歴も今回の合同FC受付1段と9/29–10/6の終了済み単独FC受付1段になったことを実DOMで確認。live.htmlがschedule.htmlへ遷移する経路も確認。
- publicEventsとlive-runtime-fallback.jsの両方で白石公演は今回合同FC1offer＋過去単独FC1offer。元sourceRowIds3件を保持。誤区分の履歴ID26a950412b87165ea9deは削除せずpublishable=false/flowEligible=false、classificationCorrection出典付きで保存。
- CANDY10/20・SWEET10/23は各1公演・2受付を保持。CANDYの終了受付申込導線なし。SWEET当落・入金マーク各1、11/16外部公演1件を実表示で再確認。
- 履歴専用39421712966は同時更新によるnon-fast-forwardで書込み拒否（データ上書きなし）。通常統合側の履歴保存・公開で今回の訂正は完了。全体公開停止ではない。ローチケ取得の部分縮退と既存保留7件は保持し、正常な更新を公開。discovery-publication-health 21:32:05 missingOffers=[]/sourceFailures=[]。
