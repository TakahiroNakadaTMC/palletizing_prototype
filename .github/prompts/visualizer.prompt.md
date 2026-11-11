---
name: visualizer
description: パレタイズ結果の3D/2D可視化・ビューアツール開発
argument-hint: 可視化対象のデータファイルやレンダリング要件
---

# 荷姿・積み順の3D/2D表示

現行の品番方式を対象にします。旧方式の編集・実行・検証・閲覧は廃止済みです。
共通規約は [copilot-instructions](../copilot-instructions.md)、
仕様は [README](../../README.md) と [制約仕様](../../constraints/constraints.md) を参照してください。

## 担当範囲と確認事項
- 版2の品番結果だけを表示する。旧結果を推測変換して表示しない。
- `python .\visualizer\serve_3d_viewer.py --results-dir .\tester\catalog_results\my_run`。
- 単独HTMLは `python .\visualizer\visualize.py <結果JSON> -o <出力HTML>`。
- 品番・仕入先・箱名称・共通モデル・固定蓋・品番別投入／配置／未配置数を表示する。
- 表示は計算時点の記録を使い、現在のDB変更で書き換えない。文字列を安全に描画する。
- 3D/2D、積み順スライダー・アニメーション、ケース別パレット寸法・荷山上限を維持する。
- 箱蓋結合外形の最小XY角・蓋込み上面Zという現行座標基準を使う。
- 計算PASSと独立検証PASSを混同しない。はみ出しは要確認として表示する。
- 実ブラウザで表示・操作・不正入力時の通知を確認する。耐荷重・安定性を保証しない。

作業後は関連テストで動作を確認し、関係するREADMEを更新してください。
