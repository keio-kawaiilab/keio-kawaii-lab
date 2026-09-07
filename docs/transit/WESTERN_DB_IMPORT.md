# 西側直通系統：全列車のDB組み込み

2026-09-07、Yahooの全件調査を既存のtransit-v2 DBに取り込んだ。
DBの索引に登録し、共通の読込処理から取得できる状態。

| 取り込んだ内容 | 件数 |
| --- | ---: |
| 掲載列車ID | 7,898 |
| 直通あり | 3,958 |
| 線内完結 | 3,940 |
| 順序付きの駅・着発レコード | 163,734 |
| 物理駅 | 248 |
| 既存駅IDとの対応がある物理駅 | 228 |
| 運転条件 | 36 |
| 日付指定・除外日などの条件がある列車ID | 483 |

掲載ID単位の件数であり、特定日の実運転本数ではない。
列車ID・駅・着発・終着・通過路線・曜日条件・出典の取込漏れは0件。

## DBの読込と更新

`data/transit-v2/index.json` の `networkJourneyFiles.western-yahoo` が列車データを指す。
`sourceCatalogs.western-yahoo` に駅・運転条件・既存ID対応表・監査を登録した。
既存の `network-journeys.json` と追加データを合わせて読む入口は次のとおり。

```python
from pathlib import Path
from transit_network_db import load_network_journeys

journeys = load_network_journeys(Path('data/transit-v2'))
western = [j for j in journeys if j.get('sourceOperator') == 'western-yahoo']
assert len(western) == 7898
```

`scripts/` をPythonのモジュール検索パスに含めて実行する。
追加ファイルはgzip JSONで、読込処理が展開し、全ファイル間のID重複を拒否する。

```bash
python scripts/import_western_train_db.py
python scripts/verify_western_train_db.py
python scripts/test_western_train_db.py
```

通常のDB再生成 `build_transit_v2.py` からもインポーターを呼ぶ。
`finalize_transit_v2.py` は追加ファイルを含めて全行程を読み、件数を集計する。
仕上げ処理後の旧断片に対して対応表と入力ハッシュを更新し、検証記録を最新に保つ。
旧索引に戻った後の再登録、繰り返し実行時の同一出力、旧データの保持を検証した。

## 保存したファイル

`data/transit-v2/western/` に以下を保存。

| ファイル | 内容 |
| --- | --- |
| `network-journeys.json.gz` | 全7,898列車。始発・終着・全着発・路線順・出典・運転条件の参照 |
| `station-catalog.json` | 248物理駅、既存駅IDとの対応、21路線の定義 |
| `calendars.json` | 曜日区分と原文の運転条件36種類 |
| `existing-fragment-matches.json.gz` | 既存の列車断片との全停車駅・着発一致の対応表 |
| `import-audit.json` | 全件会計、参照元・出力ファイルのハッシュ |

列車は `yahoo.Train:202609_03a:<掲載ID>`、物理駅は `yahoo.Station:<駅コード>` の固定キーを使う。
運転条件も固定の参照キーを持つ。Yahooの提供データとして出典を付け、鉄道事業者の公式データとは区別している。
午前0～2時台は運転日基準の24～26時台に正規化し、出典で不明な着発はnullのまま保持する。
通過する境界に停車時刻を作らず、列車全体の路線順で連続性を保持する。

## 既存データとの対応

既存の対象路線の断片14,666件を比較した。

| 比較結果 | 断片数 |
| --- | ---: |
| 全駅順・利用可能な全着発・曜日が一致し、候補が一つ | 6,618 |
| 完全一致の候補が複数 | 6 |
| 完全一致なし | 3,930 |
| 比較に必要な駅対応・着発などが不足 | 4,112 |

これは旧断片との対応状況で、7,898列車の取込漏れではない。
全行程の列車データは旧断片の推定に依存せずDBに登録した。
列車番号や数分の近さによる結合は行わず、曖昧な候補や運転条件を飛ばして旧IDを直通へ昇格させていない。
同名の別駅への対応を避けるため、既存駅IDは対象路線と物理駅の範囲で解決する。

## 検証した範囲と次工程

全件検証で7,898 ID、163,734駅レコード、全通過路線、始発・終着、出典、運転条件が一致した。
参照先不明は0件。欠落列車、1分の時刻改変、曜日違い、複数の一致候補、重複IDを検出する回帰テストも通過。
東武池袋止まりと地下鉄池袋行、東横／目黒の武蔵小杉行、臨時の西武球場前行、境界駅を通過するS-TRAINを確認した。

今回完了したのはDBへの組み込み。検索画面の `route.js` は既存v1データを使っている。
次に新しいDBの読込を検索へ接続し、運転日指定・除外日、乗降・座席条件を評価して、実際の検索で全系統を検証する。
年が書かれていない運転条件は年を推定せず原文を保持しており、条件付き列車を全平日・全休日に展開してはいけない。

[調査の全列車一覧](yahoo-western-all-trains/README.md)
