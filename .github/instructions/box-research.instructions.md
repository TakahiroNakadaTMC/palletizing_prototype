---
description: "箱仕様の調査、箱DBの追加・更新、箱と蓋の互換性確認時に使用します。"
---

# 箱仕様調査・DB管理

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- 箱本体の仕様は `box_research/catalog/box_model_db.json`、蓋は同フォルダの `lid_db.json` に記録する。
- `box_type_db.json` は品番・仕入先・現場の箱名称・共通モデル・固定蓋の対応表。
- 品番は全体で一意、箱名称は重複可能。モデル名はIDと表示名を兼ねる。
- 寸法・嵌合深さ・上縁幅を公開メーカー資料等で調べ、情報源と不確実性を `box_research/README.md` に記録する。
- `length` はL、`width` はW。寸法表示はL × W × H。既存値を推測で変更しない。
- 蓋はモデルの `compatible_lids` に存在し、品番の固定蓋と整合することを確認する。
- ID正規化・参照検証・版照合付き保存・モデル名変更確認を迂回しない。
- 移行CSVは資料であり、現在のDBを上書き生成しない。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
