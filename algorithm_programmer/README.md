# パレタイズアルゴリズム実装モジュール (algorithm_programmer/)

**文書番号:** AP-DOC-2026-001  
**作成日:** 2026-08-19  
**最終更新日:** 2026-09-23（混載エンジン MSP-EPハイブリッド化・下段オーバーサイズ制約追加）  
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

2. **混載エンジン (`palletize_mixed`)** — MSP-EPハイブリッド方式（2026-09-23改訂）:
   - **エンベロープ決定 (`_determine_mixed_envelope`)**: 投入箱構成から全層共通のX/Y作業範囲を一度だけ決定し、
     全層で使い回すことで支持率計算・四隅レベリングの一貫性を確保。
   - **層内高さグルーピング (`_choose_layer_height`)**: 同一層内に高さの異なる箱が混在すると層の上面が
     四隅で不揃いになるため、層ごとに残数最大の代表高さを選び、同一高さの箱のみをその層のパッキング対象とする
     （高さの異なる箱は後続の層に持ち越す）。
   - **Phase A - 四隅アンカリング (`_anchor_corners`)**: 各層の4隅（上端左右・下端左右）に独立した箱を
     1個ずつ優先配置。在庫僅少の最終層でも連続1行では4隅中2隅しか触れられない問題を回避し、
     `level_top_four_corners`（最上段のみ対象）でのトリミング発生を防ぐ。
   - **Phase B - 行分割＋FFD詰め (`_row_free_intervals` / `_fill_row_intervals`)**: 層をY方向に箱の代表寸法で
     行(Row)分割し、既配置箱を障害物として扱いながら空きX区間をFirst-Fit-Decreasingで充填
     （Module-Aware Strip Packing）。
   - **Phase C - Extreme Points補完 (`_ep_fill_layer`)**: 行詰めで埋まらない残渣スペースは、既配置箱の
     右端・下端から動的に候補座標を生成して追加充填。
   - **配置可否判定 (`_try_place_at`)**: 境界チェック・2D重なりチェックに加え、2層目以降は以下を必須とする:
     - 支持面判定: 直下段箱との接地面積比率85%以上（空中浮きの完全排除、`_support_ratio`）。
     - **下段オーバーサイズ制約 (`_is_oversized_support` / `_has_oversized_support`, 2026-09-23追加)**:
       支持している下段箱のいずれかが、上段箱よりも幅・奥行きの**両方とも**大きい場合は配置不可とする。
       上段箱が下段箱の縁からずれて不安定な段積みとなり荷崩れする危険があるため（同一サイズ・片方のみ
       大きい場合は許容）。`supervisor/validate.py` にも同等の独立検証項目を追加済み。
   - **レイヤーループ**: 箱在庫切れ・次層が積載高さ超過・当該層が1個も配置できない（デッドロック回避）の
     いずれかでのみ終了。旧実装にあった「層自身の四隅不一致で即break」ロジックは撤廃済み（打ち切り防止）。
   - 回転（0°/90°）の一致を強制する制約は設けていない（自由に選択可）。

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

---

## 5. 変更履歴

### 2026-09-23
- **混載エンジン全面書き換え（MSP-EPハイブリッド）**: `boundary_min_short_side`（TP-342×16+TP-332×16=32個）が
  固定グリッド方式の隙間により6/32個しか配置できなかった問題を修正。Module-Aware Strip Packing
  （行分割＋FFD詰め）を主アルゴリズムとし、Extreme Points法で残渣充填する方式に変更。結果、32/32個を配置し
  最上段四隅高さ一致（`level_top_four_corners`、最上段のみ対象）もPASS。
- **層内高さグルーピング追加**: 高さの異なる箱が同一層に混在し四隅不一致を起こす副作用を修正
  （`_choose_layer_height`）。
- **下段オーバーサイズ制約を追加**: 下段箱が上段箱より幅・奥行き両方とも大きい場合の段積みを禁止
  （`_is_oversized_support` / `_has_oversized_support`）。既存の支持面積比率85%チェックに追加する形で適用し、
  `supervisor/validate.py` にも同等の独立検証項目を追加。
- 向き（回転）の一致を強制する制約は要件により追加していない。
- 上記変更後、全13テストケース（`tester/run_tests.py` / `supervisor/validate.py`）で回帰なし・全件PASSを確認。

