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
  - `ERROR` ケースが含まれる run は明示エラーとして表示停止（黙って除外しない）
- `coordinate_reference == "combined_footprint_min_xy_top_z"`（現対応）
- `part_counts` / `boxes` / `unplaced_boxes` の数量・メタデータ整合
- manifest 件数・数量集計・result JSON (`test_name` / `catalog_revision` / 件数 / FAIL整合) を相互照合

## 備考

- 箱メタデータは結果 JSON スナップショットをそのまま使用（DB 再参照しない）
- 文字列はエスケープして表示（HTML 注入防止）
- 3D/2D 切替、積み順スライダー、再生、サマリ表示は継続
