# パレタイズアルゴリズム実装モジュール (algorithm_programmer/)

**文書番号:** AP-DOC-2026-001  
**作成日:** 2026-08-19  
**担当エージェント:** `algorithm-programmer`  
**対象読者:** `orchestrator`, `tester`, `visualizer`, `supervisor`  

---

## 1. 概要

本ディレクトリは、[`algorithm_research/proposal.md`](file:///home/tmc1475337/Workspaces/palletizing_prototype/algorithm_research/proposal.md) の提案方式および [`constraints/constraints.md`](file:///home/tmc1475337/Workspaces/palletizing_prototype/constraints/constraints.md) の荷姿制約に基づき実装されたパレタイズ計算エンジンを管理します。

---

## 2. モジュール構成

```text
algorithm_programmer/
├── models.py       # データクラス定義 (BoxSpec, PlacedBox, PalletSpec, PalletizeResult)
├── palletizer.py   # パレタイズ計算エンジン本体 (HM-Palletizer)
├── cli.py          # コマンドライン実行インターフェース
└── README.md       # 本ドキュメント
```

---

## 3. 主要ロジックと実装機能

1. **単載エンジン (`palletize_single`)**:
   - 0度/90度グリッドおよびスプリット（レンガ）分割パターンを自動生成・比較。
   - 長辺 $<1360\text{mm}$、短辺 $800\text{mm} \sim 1000\text{mm}$ の境界フィルタリング。
   - パレット中央への自動センタリングオフセット計算。
   - 勘合深さ `fitting_depth` を考慮した最大段数・Z座標計算。
   - 偶数/奇数段の反転によるインターロッキング（荷崩れ防止）。

2. **混載エンジン (`palletize_mixed`)**:
   - 拡張 Extreme Points (EP) 法 ＋ Best-Fit Decreasing 配置。
   - 嵌合Z座標ソルバー: $Z = \max_{j \in Support} (Z_{top, j} - fitting\_depth)$
   - 支持面判定: 接地面積85%以上の支持を要求（空中浮きの完全排除）。
   - TP規格のモジュール嵌合段積みボーナスと境界ペナルティ付き多目的評価関数。

3. **積み順決定 (`assign_loading_orders`)**:
   - トポロジカルソート $(Z_{base} \text{昇順} \to Y_{base} \text{昇順} \to X_{base} \text{昇順})$ により、下段優先・干渉フリーな積載順序 `order` (1..N) を付番。
   - 支持している下段箱の `order` リスト（`supported_by`）を記録。

---

## 4. 実行方法 (CLI)

```bash
# 単一テストケースの実行
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json

# 結果をJSONファイルに出力
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json -o tester/results/result_mixed_tp_same_height.json
```
