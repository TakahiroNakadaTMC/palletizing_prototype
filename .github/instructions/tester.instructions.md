---
description: "パレタイズのテスト実行、結果JSONの確認、未配置・制約違反・実行エラーの報告時に使用します。"
---

# テスト実行・結果確認の指針

- 一括実行には現行の `tester/run_tests.py` を使用してください。`test_programmer/test_case_approval.json` がある場合は、採用状態が `true` のケースだけが対象です。
- `run_tests.py` は `algorithm_programmer/cli.py` を呼び出し、`tester/results/result_<ケース名>.json` に結果を保存します。存在しない `run_simulation.py` は使用しないでください。
- 単一ケースだけを実行する場合はCLIを直接使います。採否フィルターは適用されないため、実行するJSONを明示してください。
- 結果では `input_boxes_count`、`placed_boxes_count`、`unplaced_boxes_count`、`unplaced_boxes`、`summary.is_valid`、`summary.violations` を確認してください。
- 現行ランナーはケース単位の実行エラーや制約FAILがあっても処理を続け、ケース処理後は終了コード0を返します。終了コードだけで全件成功と判断せず、標準出力・標準エラーと結果JSONを確認してください。
- 採用状態は実行対象であることを示し、制約検証に合格したことを意味しません。独立した制約検証は `supervisor/validate.py` の結果も確認してください。
- 報告には実行したケース、配置数／投入数、未配置数、制約合否・違反、実行エラーを含め、未実行ケースがあれば明記してください。
