---
description: "パレタイズのテストケース作成・編集、箱・蓋の参照整合性確認、採用状態や関連ドキュメントの更新時に使用します。"
---

# 実荷姿ケース編集・採否管理

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- 実荷姿ケースの品番・数量・固定蓋・仕入先・パレット条件は推測で変更しない。
- ケース・採用状態は `box_research/catalog/test_cases.json` の `test_cases` / `approval_state` に保存する。
- ケースは `name`、`description`、`supplier_name`、`pallet_id`、荷山上限の `pallet`、`box_list` を持つ。
- 各箱行は `{part_number, count}`。数量は整数1～500。ケースで箱IDや蓋IDを指定しない。
- 品番から共通モデルと固定蓋を照合し、パレットの仕入先適合性も確認する。
- `python .\test_programmer\serve_testcase_viewer.py` でケース編集画面を開く。
- 採用は実行対象を意味し、制約合格とは区別する。
- 保存後にケース数・数量・参照・採否を確認し、関連READMEを同期する。
- アルゴリズム検証ケースは依頼された場合だけ作成し、実荷姿ケースと区別する。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
