# LIVE・チケットカレンダー 運用手順

このページはファン向けインフラとして扱う。更新速度よりも、誤った受付・締切・公演情報を本番公開しないことを優先する。

## 基本原則

- 本番データは `data/live-events.json`。
- 公式SCHEDULE全件の照合台帳は `data/official-schedule-index.json`。5組・当月から12か月先の `LIVE` / `EVENT` を取得する。
- `eventScope` は `kawaii-lab`（主催）/ `external`（外部出演）の2値。判定は `scripts/schedule_scope.py` だけで行う。未知の催事は安全側で `external` にする。
- 全取得元を15分ごとに並列更新し、統合後の公開候補が公開前監査を通る。
- 1取得元だけが停止した場合は、その取得元の前回正常データを維持したまま、正常な取得元の新情報を公開する。取得元単位の縮退はIssueに記録し、次回巡回で自動再試行する。
- 大特典会・リリースイベントは、公式に確認できた開催日・会場を先に公開できる。受付未発表時は日程のみの状態とし、申込期間を推測しない。後続告知を取得した時点で同じ公演へ受付情報を追加する。
- 監査に失敗した候補データは commit / publish しない。前回正常版を維持する（fail closed）。
- FC限定・FC先行・アップグレードは公式情報を優先する。
- それ以外のチケットぴあ掲載受付はぴあを基準にする。
- オンライン特典会はSUKISUKIを基準にする。

## 公開前監査

`scripts/audit_schedule_release.py` が前回正常版と更新候補を比較する。

加えて `scripts/audit_official_schedule_coverage.py` が、公式SCHEDULEの全行に対応する公演・出演者・日付・公式URLが本番データに存在することを確認する。1行でも未対応なら公開しない。

自動公開を止める主な条件:

- 未来の公演・有効な受付が突然消えた
- 既存の申込締切が前倒しされた
- 既存の申込締切が根拠なしに変更された
- 未来の公演日が既存データから消えた
- 同一 `lotRlsCd` のぴあ受付が重複した
- 申込開始が締切より後になった
- FC / アップグレードをぴあ由来データとして公開しようとした
- ぴあ受付に申込詳細URL (`lotRlsCd`) がない
- 「行きたい!公演アラート」等のUI文字列が公演名に混入した
- オンライン特典会の販売情報にSUKISUKI商品URLがない
- イベント件数が異常増加した
- 公式SCHEDULEの取得失敗、件数の急減、または未収録行がある
- `eventScope` が欠落・不正、または公式照合台帳と一致しない

締切延長は、確認済みソースがある場合のみ許可し、警告として記録する。

## 監査結果

最新の成功監査は `data/schedule-health.json` に記録する。

主な項目:

- `status`: `ok` / `blocked`
- `candidateUpdatedAt`: 候補データ更新時刻
- `previousEventCount` / `candidateEventCount`
- `protectedPreviousCount`: 消失監視した未来・有効項目数
- `errorCount` / `warningCount`
- `candidateSha256`: 公開候補データのハッシュ

## 障害時

監査が `blocked` になった場合、本番データは更新しない。

GitHub Actions は `🚨 Schedule release blocked` というIssueを自動作成する。同じ障害でIssueを増殖させない。正常な全体更新が再び監査を通るとIssueを自動で閉じる。

### 緊急停止

誤掲載の疑いなど、監査結果に関係なく自動公開を止めたい場合は `data/schedule-control.json` の `freeze` を `true` にする。

```json
{
  "freeze": true,
  "reason": "確認中のため自動更新を停止"
}
```

解除時は原因を確認してから `freeze` を `false` に戻す。

## 復旧確認

1. 元の公式ページ / チケットぴあ / SUKISUKIで正しい情報を確認する。
2. パーサーまたはデータ補正ロジックを修正する。
3. 回帰テストを追加する。
4. `schedule-health.json` が `status: ok`、`errorCount: 0` になったことを確認する。
5. 本番 `schedule.html` で公演名・都道府県・申込帯・締切・リンクを確認する。
6. freeze中なら最後に解除する。

## やらないこと

- 不明な申込開始日時を推測してデータ上の事実として保存しない。
- ぴあの異なる `lotRlsCd` を同じ受付として統合しない。
- 告知記事の見出しをそのまま公演名として扱わない。
- 監査を無効化して更新を通さない。
- 異常発生時に本番データを空にして復旧しようとしない。
