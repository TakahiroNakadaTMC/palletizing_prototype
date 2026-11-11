---
description: "パレタイズのテスト実行、結果JSONの確認、未配置・制約違反・実行エラーの報告時に使用します。"
---

# ケース実行・結果確認

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- 入力は `box_research/catalog/test_cases.json`。採用状態がtrueのケースだけを一括実行する。
- `python .\tester\run_tests.py --output-dir .\tester\catalog_results\my_run`。保存先は未使用のフォルダにする。
- 単一ケースは `python .\algorithm_programmer\cli.py --catalog-case othics_6 -o <出力JSON>`。
- 一括結果の `run_manifest.json`、各結果の `input_boxes_count`・`placed_boxes_count`・`unplaced_boxes_count` を確認する。
- `input_parts`・`part_counts`・`unplaced_boxes` で品番別数量の保存と未配置理由を確認する。
- FAIL/ERRORを含む一括実行は非0終了。終了コードだけでなく一覧・診断情報も確認する。
- 採用状態、計算PASS、独立検証PASS、全箱配置を混同しない。
- 今回の結果フォルダだけをSupervisorへ渡す。既存の古い結果を使わない。
- ケース数、投入／配置／未配置数、PASS/FAIL/ERROR、未実行を区別して報告する。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
