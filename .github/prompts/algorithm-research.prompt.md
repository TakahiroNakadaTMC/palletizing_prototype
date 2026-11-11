---
name: algorithm-research
description: パレタイズアルゴリズム候補調査・比較・最適方式の提案
argument-hint: 調査対象のアルゴリズム分野や特定制約の検討観点
---

# アルゴリズム方式調査

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- `constraints/constraints.md` と現行の共通モデル・蓋DBを確認してから方式を調査する。
- レイヤー、分割、Extreme Points、モジュールブロック等を比較し、採用理由と限界を `algorithm_research/proposal.md` に示す。
- 上段箱の嵌合深さを使った高さ、箱蓋外形、支持、TP異モデル段積みの条件を数式・疑似コードで説明する。
- ケース別最大L/W/Hは境界値を含む。固定800mm下限や旧はみ出し制限を復活させない。
- 同モデル・同蓋の品番をまとめた単載判定と、品番別数量保存を両立させる。
- 実物の耐荷重・たわみ・安定性を保証しない。仕様変更は利用者の合意を得る。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
