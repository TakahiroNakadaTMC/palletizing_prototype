# テストケース編集

## 正式な保存先

ケースと実行対象状態は `box_research/catalog/test_cases.json` に保存します。
旧 `test_cases/` と `test_case_approval.json` は廃止・削除しました。

```json
{
  "schema_version": 1,
  "test_cases": {
    "sample_case": {
      "name": "sample_case",
      "description": "検証内容",
      "supplier_name": "仕入先名",
      "pallet_id": "__STANDARD_1200_1000_130__",
      "pallet": {
        "max_x_span": 1360,
        "max_y_span": 1100,
        "max_height": 1200
      },
      "box_list": [
        {"part_number": "000001", "count": 20}
      ]
    }
  },
  "approval_state": {"sample_case": true}
}
```

箱・蓋は `box_research/catalog/box_type_db.json` の品番から解決します。ケースには固定蓋や箱寸法を重複保存しません。パレット本体の寸法と利用可能な仕入先は `box_research/pallet_db.json` を参照し、ケースの `pallet` には荷山上限だけを保存します。

採用状態はテスト実行対象を選択するための設定です。制約検証に合格したことを示すものではありません。新しいケースは不採用で作成され、編集画面で採用状態を設定できます。

## 編集画面

```powershell
python .\test_programmer\serve_testcase_viewer.py
```

既定ページは品番方式のケース編集です。品番・箱モデル・蓋・パレットDBも同じ画面から編集できます。箱DBビューアサーバーからは `/catalog_cases.html` で開けます。

保存はカタログ全体の読込時リビジョンに基づいて競合を検出します。古い画面からの保存は拒否されるため、再読み込みして変更を確認してください。ケースが参照する品番・パレットや、品番が使うモデル・蓋を削除・変更する場合はサーバーが整合性を検証します。

旧ケースAPIは `410 Gone` で明示的に拒否され、旧画面のブックマークはケース編集画面へ転送されます。

## 回帰テスト

```powershell
python -m unittest box_research.catalog_store_test box_research.catalog_http_test box_research.database_validation_test
$env:PALLETIZER_RUN_BROWSER_TESTS = "1"
python -m unittest box_research.catalog_ui_test
```
