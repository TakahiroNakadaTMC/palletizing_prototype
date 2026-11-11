---
name: algorithm-programmer
description: パレタイズアルゴリズムの実装・改善と制約充足の検証
argument-hint: 修正対象の制約項目やテスト失敗内容
---

# パレタイズ計算実装

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- `algorithm_programmer/catalog.py` で品番を共通モデル・固定蓋へ解決し、コアエンジンへ渡す。
- ケースの `box_list` は `{part_number, count}`。品番の蓋をケースで上書きしない。
- 同モデル・同蓋はまとめて計算し、確定した積み順に入力順で品番を配分する。
- 結果は版2の品番方式。`box_id` は現場の箱名称で、`part_number`・仕入先・モデル・蓋・品番別数量を別途記録する。
- 単一ケースは `python .\algorithm_programmer\cli.py --catalog-case othics_6 -o <出力JSON>`。
- TP異モデル段積みを一律禁止せず、非TP・外嵌めTPの外形一致と単一支持も維持する。
- 回転0/90度・天地固定、支持率85%以上、上段箱の嵌合深さ、センタリング・支持サイズ制限を守る。
- Supervisorと計算側の判定一致、品番数量保存、未配置理由をテストする。配置不能や不正入力を明示する。
- コアの寸法キーや座標の意味を変えない。詳細ルールは制約仕様を正とする。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
