# パレタイズアルゴリズム試作

空箱と蓋をパレットに積み、配置・積み順・未配置数を計算する試作ツールです。
物理的な耐荷重・たわみ・輸送中の安定性を保証するものではありません。
荷姿のルールは [制約仕様](constraints/constraints.md) を参照してください。

## データ構成

**品番方式だけを使用します。旧方式のDB・ケース・結果は使用できません。**

| データ | 保存先 | 役割 |
|---|---|---|
| 品番・箱種 | [box_type_db.json](box_research/catalog/box_type_db.json) | 品番、仕入先、現場の箱名称、共通モデル、固定蓋 |
| 共通箱モデル | [box_model_db.json](box_research/catalog/box_model_db.json) | 箱本体の寸法、嵌合深さ、規格、互換蓋 |
| 蓋 | [lid_db.json](box_research/catalog/lid_db.json) | 蓋の寸法・嵌め方 |
| ケース・採用状態 | [test_cases.json](box_research/catalog/test_cases.json) | 品番と数量、仕入先、パレット、荷山上限、実行対象 |
| パレット | [pallet_db.json](box_research/pallet_db.json) | パレット本体の寸法と利用する仕入先 |
| 移行・名称変更履歴 | [migration.json](box_research/catalog/migration.json) | 移行時の記録とモデル名変更履歴 |

元の [CSV](box_research/box_list.csv) は資料として残しますが、運用時には読み込みません。
旧DB・旧ケースはGitの履歴で確認できます。復元して運用しないでください。

### 品番とモデルの違い

- **品番**は現場で使う識別子です。ケースでは品番と数量を指定します。
- **共通モデル**は実物の箱の仕様です。品番が違っても同じモデルなら同じ箱として判定します。
- **蓋**は品番に登録したものを自動使用します。ケースごとの指定変更はできません。
- 同じモデル・同じ蓋はまとめて単載計算し、確定した積み順へ入力順で品番を配分します。
  返却数量の割合を平準化する機能は未実装です。
- TP箱の異なるモデル同士の段積みは、従来の嵌合・支持条件を満たせば可能です。
- 結果の `box_id` は現場の箱名称です。品番は `part_number` に別途記録します。

## 使い方（Windows PowerShell）

### 1. DB・ケースを編集する

```powershell
python .\box_research\serve_viewer.py
python .\test_programmer\serve_testcase_viewer.py
```

DB画面は通常 `http://localhost:8081`、ケース画面は通常 `http://localhost:8083` です。
実際のURLは起動時の表示を確認してください。
品番・モデル・蓋・パレット・ケースを新画面で管理します。
採用状態は「実行するかどうか」であり、制約検証に合格したことではありません。
モデル名変更時には、影響する対応付けを確認してから確定します。

### 2. 採用済みケースを計算する

```powershell
python .\tester\run_tests.py
```

結果は実行ごとの新規フォルダに保存します。保存先を指定する場合は未使用の名前を使います。

```powershell
python .\tester\run_tests.py --output-dir .\tester\catalog_results\my_run
```

単一の保存済みケースを計算する場合：

```powershell
python .\algorithm_programmer\cli.py --catalog-case othics_6 -o .\tester\catalog_results\result_othics_6.json
```

### 3. 独立検証する

計算処理とは別の処理で、現在のDB・ケースとの一致、数量、配置、支持関係を検証します。
一括実行が表示した結果フォルダを指定してください。

```powershell
python .\supervisor\validate.py --results-dir .\tester\catalog_results\my_run --report-dir .\supervisor\catalog_reports\my_run
```

結果フォルダには `run_manifest.json`（実行したケースの一覧）が必要です。
DB・ケース・パレットを変更した場合は再計算してください。
計算結果のPASS表示だけで独立検証PASSとは判断しません。
計算時の集計と独立検証の集計は分けて記録します。
ケースごとの実行エラーや判定の食い違いも、詳細レポートに残します。

### 4. 3D表示する

```powershell
python .\visualizer\serve_3d_viewer.py --results-dir .\tester\catalog_results\my_run
```

通常は `http://localhost:8082` を開きます。品番別の数量、3D/2D、積み順を確認できます。
結果は計算時点の記録として表示し、現在のDBで書き換えません。
旧形式の結果は表示できません。現行ケースから再計算してください。

### 結果の見方

- **PASS**：配置した荷姿が制約に適合すること。全箱配置を意味しません。
- **FAIL**：制約に適合しないこと。
- **ERROR**：入力不整合などで実行できなかったこと。
- **未配置**：投入したが積載できなかった箱。品番別の数量と理由を確認します。
- **はみ出し要確認**：確認情報です。はみ出し量だけではFAILにしません。

FAIL・ERRORを含む一括実行は終了コードが非0になります。
結果一覧と数量を確認し、終了コードだけで判断しないでください。

## 構成と開発

| 領域 | 内容 |
|---|---|
| [box_research](box_research/) | DB・共通保存処理・編集画面 |
| [test_programmer](test_programmer/) | ケース編集サーバー |
| [algorithm_programmer](algorithm_programmer/) | 共通モデルによる計算、品番の割り当て |
| [tester](tester/) | 採用済みケースの一括実行 |
| [supervisor](supervisor/) | 計算から独立した制約・数量検証 |
| [visualizer](visualizer/) | 結果の3D/2D・積み順表示 |
| [.github/agents](.github/agents/) | 開発を補助する各ロールの定義 |

Python 3.8以降の構文を対象とします。寸法は **L × W × H**、単位はmmです。
DBの `length` はL、`width` はWです。結果の回転後X/Y寸法とは区別してください。
パレットはLがW以上になるよう登録します。逆の場合はエラーを表示し、自動で入れ替えません。

```powershell
python -m unittest discover -s algorithm_programmer -p "*_test.py"
python -m unittest discover -s box_research -p "*_test.py"
python -m unittest discover -s supervisor -p "*_test.py"
python -m unittest discover -s visualizer -p "*_test.py"
python -m unittest discover -s tester -p "*_test.py"
```

各領域のテスト実行方法は、その領域のREADMEも参照してください。
ケース編集サーバーは `box_research` の共通HTTP・画面テストで検証します。
`test_programmer` 単独にはPythonテストがないため、そこへのテスト探索は実行しません。
JavaScriptのガイド描画・現行画面の構文テストは、Node.jsが利用できる環境で実行します。

```powershell
node --test .\visualizer\guide_logic.test.js
```

旧ケース生成・旧一括ループスクリプトは廃止しました。

## 旧方式廃止時の検証結果

旧DB・旧ケースを削除した状態で現行150ケースを再計算し、独立検証しました。
結果は148件PASS・2件FAIL・実行エラー0件、
投入3132箱・配置2588箱・未配置544箱です。
`aisin_10_m20` と `othics_m20` は配置0箱の既知FAILです。
全150件で品番・配置座標・回転・積み順・支持関係・数量が廃止前の結果と一致しました。
品番362件・共通モデル81件・蓋24件・ケース150件と、その登録値は変更していません。
生成結果・レポートはGit管理外です。

回帰テスト213件中211件合格、環境依存のブラウザ試験2件はスキップしました。
別途、実際のEdgeをCDP（ブラウザの操作用接続）から操作し、DB・ケースの一覧と編集画面、
統合ビューアの150件読み込み・3D/2D・積み順、単独HTML表示を確認しました。
旧データなしのカタログをCRLFへ変換しても、内容と照合値が変わらないことも確認済みです。

## 廃止後の整合性修正

独立検証のエラー記録、仕入先の複数行入力、計算中のDB変更への対策、
パレットのL/W順、モデル改名の確認手順、結果一覧の照合、テスト対象、説明書を修正しました。
登録済みのDB値と配置エンジンは変更していません。

Pythonテスト227件中225件合格・ブラウザ試験2件スキップ、JavaScriptテスト15件合格。
編集画面は別途実際のEdgeで確認し、仕入先2行の保存・再読込も確認しました。
結果画面も実際のEdgeで150件の読込・3D/2D・積み順と、ERROR時の明示的な表示停止を確認しました。
150ケースを再計算・独立検証し、148件PASS・既知の2件FAIL・実行エラー0件。
配置・積み順・支持関係・品番別数量は修正前と全件一致しています。
