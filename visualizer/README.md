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

- 箱メタデータは結果 JSON スナップショットをそのまま使用（DB 再参照しない）
- 文字列はエスケープして表示（HTML 注入防止）
- 3D/2D 切替、積み順スライダー、再生、サマリ表示は継続

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
