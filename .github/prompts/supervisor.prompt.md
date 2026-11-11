---
name: supervisor
description: パレタイズ結果の制約違反検証・品質監視・改善指示
argument-hint: 検証対象の結果データファイルパスや特定チェック項目
---

# 独立制約検証・品質監視

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- `supervisor/catalog_validation.py` と `validate.py` で版2の品番結果だけを検証する。
- `python .\supervisor\validate.py --results-dir .\tester\catalog_results\my_run --report-dir .\supervisor\catalog_reports\my_run`。
- 実行一覧と採用ケース、現在のDB版、品番・モデル・固定蓋・仕入先・パレット条件・数量を照合する。
- 計算エンジンの合否を信用せず、干渉・嵌合・支持・回転・積み順・センタリングを独立して再検証する。
- ケース最大L/W/Hは境界値を含む。はみ出し量は警告として合否と分ける。
- 上載せパレット支持、非TP同モデル、外嵌めTP同蓋・外形一致・単一支持、通常TP異モデルの条件を守る。
- DB編集後の古い結果、不正数量、改ざん、実行一覧不足は明示的なエラーにする。
- FAILは具体的な箇所・実測値・条件を報告し、修正後に再実行・再検証する。
- 品番別数量、未配置、実行エラー、制約FAILを区別して報告する。PASSだけで全箱配置とは判断しない。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
