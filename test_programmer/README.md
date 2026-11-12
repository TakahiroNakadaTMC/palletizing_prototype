# テストケース編集

## 正式な保存先

ケースと実行対象状態は `box_research/catalog/test_cases.json` に保存します。
旧 `test_cases/` と `test_case_approval.json` は廃止・削除しました。

```json
{
  "schema_version": 2,
  "test_cases": {
    "sample_case": {
      "name": "sample_case",
      "description": "検証内容",
      "supplier_name": "仕入先名",
      "skid_id": "0001AA",
      "box_list": [
        {"part_number": "000001", "count": 20}
      ]
    }
  },
  "approval_state": {"sample_case": true}
}
```

箱・蓋は `box_research/catalog/box_type_db.json` の品番から解決します。
パレットID・荷山上限は `box_research/catalog/skid_db.json` のKEY2からその都度解決し、
パレット本体の寸法は `box_research/pallet_db.json` を参照します。ケースにはこれらを重複保存しません。
1ケースは1つのKEY2だけを使い、別KEY2の品番は混ぜません。

採用状態はテスト実行対象を選択するための設定です。制約検証に合格したことを示すものではありません。新しいケースは不採用で作成され、編集画面で採用状態を設定できます。

## 編集画面

```powershell
python .\test_programmer\serve_testcase_viewer.py
```

既定ページは品番方式のケース編集です。上部の「DB編集」リンクを開くと、品番・箱モデル・蓋・パレット・スキッド・仕入先対応表を編集できます。箱DBビューアサーバーからは `/catalog_cases.html` でケース編集を開けます。

仕入先→KEY2を選び、一覧の使用する品番だけ数量を入力します。
空欄・0は不使用、整数1〜500は保存、負数・小数・文字・501以上はエラーです。
全品番が不使用なら保存できません。使用する品番数と合計箱数を確認して保存します。
既存ケースの品番の入力順は維持します（計算後の品番配分に使うため）。
パレット・荷山上限は確認専用です。変更は「スキッドDB」タブで行い、関連ケースすべてに反映します。
設定未登録のKEY2は新規ケース作成・計算ができません。既存ケースの数量編集は可能です。
スキッドの最終更新日時はケース画面で確認できます。変更履歴は上部の「DB編集」リンクから
「スキッドDB」タブを開き、対象スキッドの編集画面で確認します。
スキッド保存前には影響ケースと変更前後を確認し、履歴をDBに保存します。
使用中の候補品番・KEY2の削除は拒否されるため、先に関連ケースを修正してください。
スキッドIDは「仕入先4桁＋工区1文字＋出荷場3文字または空欄＋コース1文字」で構成します。
「スキッドDB」タブの4項目からIDを変更すると、確認後に関連ケースの参照も更新されます。
「仕入先」の数字と「仕入先名」は別項目で、数字から対応表を使って名前を自動表示します。
未登録の数字は「仕入先対応表」タブで先に登録します。
ID変更後もケースの数量・品番順序・採用状態は維持します。

保存はカタログ全体の読込時リビジョンに基づいて競合を検出します。古い画面からの保存は拒否されるため、再読み込みして変更を確認してください。ケースが参照する品番・パレットや、品番が使うモデル・蓋を削除・変更する場合はサーバーが整合性を検証します。

旧ケースAPIは `410 Gone` で明示的に拒否され、旧画面のブックマークはケース編集画面へ転送されます。

## 回帰テスト

```powershell
python -m unittest box_research.catalog_store_test box_research.catalog_http_test box_research.database_validation_test
$env:PALLETIZER_RUN_BROWSER_TESTS = "1"
python -m unittest box_research.catalog_ui_test
```
