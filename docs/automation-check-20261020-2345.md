# 2026-10-20 23時台 公式照合・大分公演受付リンク訂正

## 根拠

- https://eplus.jp/sf/detail/3923750001-P0030012P021001 は 2026/11/30 福岡サンパレス 17:30開場/18:30開演。
- https://eplus.jp/sf/detail/3923750001-P0030013P021001 は 2026/12/1 大分iichikoグランシアタ 17:30開場/18:30開演。
- 両方の一般発売は9/26 10:00–11/29 20:00。ただし日付・会場・申込先が異なるため別公演。

実公開DOMで12/1公演の申込ページと販売フロー内リンクがP0030012（福岡）を向いていた。最新rawには大分P0030013があるが、旧bundle由来のpublicEvents内offerが先に採用されていた。

## 修正

raw単日行と、公演単位の受付生成の両方で、CANDY TUNE・12/1・18:30・eplus・当該一般発売期間・旧福岡URLが全て一致するものだけ大分URLへ訂正。旧bundleから再導入されても同じcanonical offerとなる。元の取得ID、期間、公演日・時刻は不変。11/30を含む別公演・別受付は変更しない。履歴の誤リンク観測は削除せず、非公開/フロー不適格と訂正根拠を付けて保存。正常な大分受付履歴を使用する。

関連86回帰テスト成功。実publicEventsの2公演で大分リンク1本への再生成も検証。main source変更後は既存の収集・監査・生成・公開経路で反映し、実画面を最終確認する。

6系統公式トップ・NEWS・SCHEDULEを再読。新しい対象公演/受付変更なし（CUTIE10/23追加はTV番組で対象外）。今夜23:59締切のCUTIE92733・FZ92554・中央FC92282本文、翌日MORE90316、SUKISUKI4623販売終了と4625当落/入金日を再確認。CANDY本日オン特、SWEET10/23・11/16、白石公演の既修正は維持。最新全体監査22:55 errorCount=0、discovery公開漏れ0・保留7、ローチケ取得の部分縮退継続。全体公開停止なし。

## 公開完了確認

- ソースe420989bf8c6effbe315f0d63131f5375e1509db。canonical migrate39442047131とTicket flow release check39442047105成功。公開ガードfa6554fbd6d523ffbd85fffdb4ddefa36929a28bのPages39442170708成功後、通常schedule.htmlの大分申込ボタン・フロー内リンクがP0030013へ変わったことを確認。
- その後、通常全取得元収集・統合39442090094成功、公開データcf48b23083e1442add5fe667f5a62c5066adec0c（23:54:38）、Pages39443560736 successまで確認。通常URLを再読し、大分の申込ボタンと販売フロー内リンクは双方P0030013、福岡は双方P0030012を向く。別日を混同せず各1公演を保持。
- publicEventsとlive-runtime-fallback.jsの両方で大分一般発売offer1件、期間9/26 10:00–11/29 20:00不変。元sourceRowIds保持。履歴ID5835d2d64e391fe3b3c5はfirstSeenAt=2026-09-27T07:09:37+09:00とobservedWindowsを保持し、publishable=false/flowEligible=false・correctSourceUrlを保存。大分P0030013の有効な受付履歴を保持。
- 全体監査23:54:09 status=ok/errorCount=0。discovery-publication-health23:54:40 missingOffers=[]/sourceFailures=[]、既存保留7件。
- 本文補完39442047217は収集・28回帰テスト・監査・生成後、別の公開ジョブとのJSON/HTML rebase競合で安全に書込み拒否。履歴専用39442047373も書込み競合。今回の訂正と履歴保存は上記通常統合・公開で完了し、上書きや監査無効化はしていない。
