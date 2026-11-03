---
description: "パレタイズのテストケース作成・編集、箱・蓋の参照整合性確認、採用状態や関連ドキュメントの更新時に使用します。"
---

# テストケース作成・編集の指針

- 現行のテストケースは実際の荷姿を記録したものとして扱います。根拠なく投入数量・蓋の指定・パレット条件を推測または変更しないでください。
- 単載・混載・境界値・非TP箱のコラム積みなどのアルゴリズム検証ケースは、依頼された場合に作成し、実荷姿ケースと目的を混同しないでください。
- 保存前に各 `box_id` を `box_research/box_db.json`、各 `lid_id` を `box_research/lid_db.json` と照合し、蓋が箱の `compatible_lids` に含まれることを確認してください。
- ケースは `test_programmer/test_cases/` に保存し、現行スキーマの `name`、`description`、`pallet` と、`box_id`・`count`・`lid_id` を含む `box_list` を使用してください。
- 実行対象の選択は `test_programmer/test_case_approval.json` で管理してください。採用状態はテスト実行対象であることを示し、制約検証に合格したことを意味しません。
- 変更後はJSONの妥当性、参照先、ケース数、投入数量、採用状態を確認し、`test_programmer/README.md` の記載も同期してください。
- 廃止した `generate_testcases.py` の手順は使用せず、テストケースビューアでケースを作成・編集してください。
