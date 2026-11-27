# visualizer

品番方式（`schema_version: 2` / `input_mode: "part_number"`）専用の 3D/2D 可視化ツールです。
旧結果（legacy）は表示対象外で、読み込み時に明示的にエラーになります。

## 構成

- `serve_3d_viewer.py` 統合ビューア HTTP サーバー
- `index.html` 統合ビューア UI
- `visualize.py` 単体結果 JSON → スタンドアロン HTML 生成
- `result_identity.js` 品番メタデータ検証・表示補助
- `part_result_support.py` 実行フォルダ選択・結果検証ヘルパー

## 使い方

### 統合ビューア

```powershell
python .\visualizer\serve_3d_viewer.py
```

- 引数なし: `tester/catalog_results` から **最新 run_manifest 実行フォルダ** を選択して厳密検証
  - 最新 run が不正なら起動エラー（古い run へフォールバックしない）
- `--results-dir` 指定可（run_manifest.json を含む実行フォルダ）
- 一覧にはPASS・FAIL・ERRORのすべてを残し、全体の件数を表示します。
  最初は表示可能なケースを選びます。全件ERRORでも起動できます。
- テスト結果はプルダウンに加え、「前へ」「次へ」ボタンでも切り替えられます。実行一覧の順番で移動し、先頭・末尾では該当するボタンが無効になります。ERRORの結果も移動対象です。
- PASS・FAILは3D/2D表示、ERRORはケース名とエラー理由を表示します。
  ERROR選択時は直前の荷姿・数量・箱の詳細を消し、再生・積み順・視点操作を無効にします。
  ERRORの数量は不明であり、0箱として表示しません。
- 最新選択は起動時のみです。起動後の再計算結果へ自動では切り替わりません。

```powershell
python .\visualizer\serve_3d_viewer.py --results-dir .\tester\catalog_results\phase5_verified
```

### スタンドアロン HTML 生成

```powershell
python .\visualizer\visualize.py .\tester\catalog_results\phase5_verified\result_othics_6.json -o .\visualizer\generated_viewers\othics_6.html
```

- 直接 JSON を指定して生成できます
- ただし入力は品番方式のみ（旧結果は拒否）

## 検証ルール（表示前）

- `schema_version == 2`
- `input_mode == "part_number"`
- `run_manifest.source == "catalog_store"`
- `run_manifest.catalog_revision` は空でない文字列
- `run_manifest.started_at/completed_at` は ISO 日時かつ時系列整合
- `run_manifest.cases` は case 名・result_file 重複なし
- `run_manifest.status` は `PASS` / `FAIL` / `ERROR` のみ
  - 正常な `ERROR` 行は除外せず、理由付きで表示する（結果JSONは要求しない）
  - ERROR行の形式不正、PASS/FAIL結果の欠落・破損・不一致は全体の表示を停止する
- `coordinate_reference == "combined_footprint_min_xy_top_z"`（現対応）
- `part_counts` / `boxes` / `unplaced_boxes` の数量・メタデータ整合
- manifest 件数・数量集計・result JSON (`test_name` / `catalog_revision` / 件数 / FAIL整合) を相互照合

## 備考

- 上部のケース集計の近くに、品番別内訳（品番・共通モデル・蓋・投入数・配置数・未配置数）を表示します。品番が多い場合は一覧内をスクロールできます。
- ケース集計には、実際の荷姿外寸とは分けて「荷山最大外形（上限） L×W×H」を表示します。Hはパレット上面からの荷物高さです。
- 未配置箱の一覧には品番・数量・箱本体外寸 L×W×H・理由を表示します。寸法を持たない過去の結果は「寸法未記録」と表示します。新しい計算結果にはモデルDBの箱本体寸法を記録します（配置計算は変更しません）。
- ケース集計にはパレットからのはみ出し量と、はみ出しだけを理由とする警告を表示しません。計算結果・制約判定・保存データは変更しません。
- 箱メタデータは結果 JSON スナップショットをそのまま使用（DB 再参照しない）
- 3D箱ラベルは積み順番号に続けて「共通モデルID / 蓋ID」（例: `1: M-A / L-A`）を表示します。その他の一覧・数量・詳細表示では従来どおり品番と箱名称を表示します。
- 箱詳細インスペクタは上部サマリーの下に配置し、画面サイズや上部表示の高さが変わった場合も追従します。画面幅に応じて横幅を広げ、高さが足りない場合はインスペクタ内をスクロールできます。
- 上部サマリーを開閉してもテスト結果の選択欄は移動しません。視点切替ボタンは選択欄やサマリーと重ならない位置に調整されます。
- 箱詳細インスペクタの品番・箱名称・仕入先・共通モデル・蓋は、重複を避けて表示します。
- 文字列はエスケープして表示（HTML 注入防止）
- 3D/2D 切替、積み順スライダー、再生、サマリ表示は継続
- 原点 `(0, 0, 0)` に色分けしたXYZ方向の矢印を表示します。2D視点では画面上に投影できる軸だけを表示します。
- 箱の配置座標には、数値文字を使わない目印を表示します。目印は現在の積み込み手順までに表示される箱だけに付き、拡大率にかかわらず視認しやすい大きさで表示します。箱の奥行き順に描画するため、手前の箱が奥の目印を隠す場合があります。座標値・座標基準は結果データのまま変更しません。

## 回帰テスト

```powershell
python -m unittest visualizer.catalog_viewer_test
node --test .\visualizer\guide_logic.test.js
```

実Edgeの混在・全件ERROR・切替・遅延応答テストは、既存のPlaywright導入済み環境で実行します。
外部CDNのスクリプトをテスト時だけ外し、ローカルの描画・表示ロジックを検証します。

```powershell
$env:PALLETIZER_RUN_BROWSER_TESTS = "1"
.\venv\Scripts\python.exe -m unittest visualizer.catalog_viewer_test.ViewerCatalogTests.test_browser_mixed_and_all_error_runs
```
