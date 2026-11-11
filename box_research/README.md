# 品番カタログと箱・蓋・パレットDB

## 正式データ

| ファイル | 内容 |
|---|---|
| `catalog/box_type_db.json` | 品番ごとの仕入先・現場箱名称・共通箱モデル・固定蓋 |
| `catalog/box_model_db.json` | 計算に使う箱寸法、嵌合、支持点、互換蓋 |
| `catalog/lid_db.json` | 蓋の仕様 |
| `catalog/test_cases.json` | テストケースと実行対象状態 |
| `catalog/migration.json` | 過去の移行内容・旧名称対応・モデル名変更履歴の監査記録 |
| `pallet_db.json` | 物理パレット仕様。従来と同じ保存場所 |

`box_list.csv` は資料であり、運用時には読み込みません。
`catalog/migration.json` の移行元ハッシュ・旧名称対応・ケース対応表は監査記録として保持し、
現在の参照整合性判定には使用しません。モデル名変更履歴は、旧名称の再利用防止などの
現在の編集保護にも使用します。

各品番の固定蓋は品番DB、使用可能な蓋は共通箱モデルDBで管理します。ケースには `part_number` と `count` を保存し、箱モデルと蓋は品番DBから解決します。ケースの `pallet_id` はパレットDBを参照します。ケースで選択した荷山上限は `pallet.max_x_span`、`pallet.max_y_span`、`pallet.max_height` です。

## 編集画面

箱・蓋・品番・ケースを編集するには:

```powershell
python .\box_research\serve_viewer.py
```

既定の `/` は品番・箱モデル・蓋・パレットDB画面を開きます。ケース専用画面は `/catalog_cases.html` です。

テストケースサーバーから開く場合:

```powershell
python .\test_programmer\serve_testcase_viewer.py
```

このサーバーの既定画面はケース編集です。どちらのサーバーも同じカタログAPIと保存先を使います。

編集内容は「変更をまとめて保存」で保存します。複数画面から同時に編集した場合、古い版からの保存は拒否されるため、再読み込みして変更内容を確認してください。保存処理はカタログ一式と `pallet_db.json` をロック下で更新し、途中で失敗した場合は更新済みファイルを復元します。カタログの版番号にはパレットDBも含まれます。LF/CRLF の差は版番号に影響しません。

現在のケースから参照されている品番・パレットは削除できません。品番が使う箱モデル・固定蓋、モデルが互換蓋として使う蓋も削除できません。使用中のモデルを通常保存で参照と同時に削除することもできません。パレットの削除・寸法・利用仕入先変更は、ケースとの整合性をサーバーで再検証します。パレット本体は長さLが幅W以上である必要があります。利用可能な仕入先は1行に1件入力します。標準パレットは固定です。モデル名の変更は影響する品番・ケースを表示して確認した後に保存し、旧名称の再利用を防ぎます。移行情報と名前変更履歴は通常保存では変更できません。

旧DB・ケースAPIへの書き込みは `410 Gone` で明示的に拒否します。旧画面のブックマークは新しい編集画面へ転送されます。

## 検証

```powershell
python -m unittest box_research.catalog_store_test box_research.catalog_http_test box_research.database_validation_test
```

ヘッドレス Edge の画面操作テストは明示的に有効化して実行します:

```powershell
$env:PALLETIZER_RUN_BROWSER_TESTS = "1"
python -m unittest box_research.catalog_ui_test
```
