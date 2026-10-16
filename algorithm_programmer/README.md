# パレタイズアルゴリズム実装モジュール (algorithm_programmer/)

**文書番号:** AP-DOC-2026-001  
**作成日:** 2026-08-19  
**最終更新日:** 2026-10-14（混載配置の探索改善）
**担当エージェント:** `algorithm-programmer`  
**対象読者:** `orchestrator`, `tester`, `visualizer`, `supervisor`  

---

## 1. 概要

本ディレクトリは、[アルゴリズム提案](../algorithm_research/proposal.md) の提案方式および
[荷姿制約](../constraints/constraints.md) に基づき実装されたパレタイズ計算エンジンを管理します。

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

   - 長辺荷姿幅 $800\text{mm} \le X_{span} < 1360\text{mm}$、
     短辺荷姿幅 $800\text{mm} \le Y_{span} < 1100\text{mm}$ の境界フィルタリング。
   - パレット中央への自動センタリングオフセット計算。
   - 最下段箱の回転後底面辺が335 mm以下の場合、蓋を含む外形の片側はみ出しを
     `PalletSpec.max_small_edge_overhang_mm` 未満に制限（既定30 mm）。
   - 勘合深さ `fitting_depth` を考慮した最大段数・Z座標計算。
   - 偶数/奇数段の反転によるインターロッキング（荷崩れ防止）。

2. **混載エンジン (`palletize_mixed`)** — MSP-EPハイブリッド方式（2026-09-23改訂）:
   - **探索範囲 (`_determine_mixed_envelope`)**: X/Yの許容上限から既存の1 mmの余裕を引いた範囲を使う。
     Y範囲を最小箱寸法の整数倍に固定せず、異なる行奥行きの合計も試す。支持率・センタリング・小辺はみ出し制約は別途確認する。
   - **層候補の比較 (`_choose_layer_height` / `_mixed_layer_candidate_score`)**: 配置高さに収まる箱を高さごとに
     パッキングし、四隅の揃い方、配置数、次段の高さ余裕を比較して採用する候補を決める。
   - **Phase A - 四隅アンカリング（廃止）**: `_anchor_corners` による各層四隅への先置きは行わない。
     先置きが行分割詰めを妨げ、箱間に隙間を作ったため無効化された。
   - **Phase B - 行分割＋FFD詰め (`_row_free_intervals` / `_fill_row_intervals`)**: 層をY方向に箱の代表寸法で
     行(Row)分割し、既配置箱を障害物として扱いながら空きX区間をFirst-Fit-Decreasingで充填
     （Module-Aware Strip Packing）。
   - **複数の行組み合わせ (`_mixed_layer_candidates`)**: 探索途中の配置を最大16通り残し、候補ごとに箱の残数を管理する。
     新しい探索では344 mmと345 mmのような近い行奥行きも区別する。従来の行詰め結果も候補に含め、四隅・配置数で比較する。
   - **上段までの比較 (`_palletize_mixed_layout`)**: 最下段候補を最大16通り試し、それぞれ上段まで積む。
     四隅高さ調整後に再センタリングし、寸法・四隅などの合否、最終配置箱数、最高高さの順で選ぶ。
     全組み合わせの探索ではないため、最大配置数を保証するものではない。
   - **Phase C - Extreme Points補完 (`_ep_fill_layer`)**: 行詰めで埋まらない残渣スペースは、既配置箱の
     右端・下端から動的に候補座標を生成して追加充填。
   - **配置後の四隅高さ調整 (`level_top_four_corners`)**: 全層の配置後に最上段四隅の高さを確認する。
     高さが揃わない場合は低い角に合わせて高い箱を除外することがある。この後処理は四隅への先置きではなく、
     配置済みの箱を削る場合があるため、最終配置数が減ることがある。
   - 最下段の335 mm以下の辺に対するパレット端はみ出し制限は、候補追加時と配置位置調整時に適用する。
   - **配置可否判定 (`_try_place_at`)**: 境界チェック・2D重なりチェックに加え、2層目以降は以下を必須とする:
     - 支持面判定: 直下段箱との接地面積比率85%以上（空中浮きの完全排除、`_support_ratio`）。
     - **下段オーバーサイズ制約 (`_is_oversized_support` / `_has_oversized_support`)**:
       直接支持している下段箱のいずれかが、上段箱よりも幅・奥行きの**両方とも1.0mmを超えて**大きい場合は配置不可とする。
       上段箱が下段箱の縁からずれて不安定な段積みとなり荷崩れする危険があるため（同一サイズ・片方のみ
       大きい場合は許容）。`supervisor/validate.py` にも同等の独立検証項目を追加済み。
   - **レイヤーループ**: 箱在庫切れ・次層が積載高さ超過・当該層が1個も配置できない（デッドロック回避）の
     いずれかでのみ終了。旧実装にあった「層自身の四隅不一致で即break」ロジックは撤廃済み（打ち切り防止）。
   - 回転（0°/90°）の一致を強制する制約は設けていない（自由に選択可）。

3. **積み順決定 (`assign_loading_orders`)**:
   - トポロジカルソート
     $(Z_{base} \text{昇順} \to Y_{base} \text{昇順} \to X_{base} \text{昇順})$
     により、下段優先・干渉フリーな積載順序 `order` (1..N) を付番。
   - 支持している下段箱の `order` リスト（`supported_by`）を記録。

---

## 4. 実行方法 (CLI)

### 配置結果の座標基準

結果JSONは `coordinate_reference: "combined_footprint_min_xy_top_z"` を記録します。
`position.x/y` は回転後の箱本体と蓋を合わせた外接形状の最小角、`position.z` は蓋込み上面です。
箱本体寸法は従来どおり `dimensions.width/length`、蓋込み高さは `dimensions.height` に保持します。
内部のパレタイズ計算では箱本体底面基準を使用し、シリアライズ時に結果座標へ変換します。

`coordinate_reference` のない既存結果は、従来の箱本体底面角の座標として扱います。

```bash
# 単一テストケースの実行
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json

# 結果をJSONファイルに出力
python3 algorithm_programmer/cli.py \
  test_programmer/test_cases/mixed_tp_same_height.json \
  -o tester/results/result_mixed_tp_same_height.json
```

---

## 5. 変更履歴

### 2026-10-14

- 混載Y探索範囲の固定を解除し、複数の行の組み合わせと最下段から上段までの試行を追加。物理的な積載制約は変更していない。
- `outer_cover_test` は修正前16箱・短辺寸法不足から、48箱・Supervisor合格に改善。
  最下段はTP-331が6箱、90度回転のTP-341が2箱で、荷姿は1032 x 1033 x 922 mm。
- 提案されたTP-341が4箱、TP-331が3箱の1032 x 1034 mm配置も候補に残ることを回帰テストで確認。
- 全27ケースをメモリ上で再実行し、Supervisor全件合格、配置数減少なし、合計1062箱から1258箱に改善。
- 配置計算の合計時間は約0.15秒から約3.4秒へ増加。`outer_cover_test` は約0.42秒、最も重いケースは約0.8秒（この環境での参考値）。
- `python -m unittest supervisor.validate_test -v` で、混在奥行き・候補上限・残数保存・奥行き上限・最終荷姿を含む15テストが合格。

### 2026-10-12

- 最下段箱の回転後底面幅または奥行きが335 mm以下の場合、対応するパレット端から30 mm以上はみ出す配置を禁止。
  外嵌め蓋の突出も判定対象とし、上限は `PalletSpec.max_small_edge_overhang_mm` で変更可能。
- 単載・混載アルゴリズムとSupervisorに制約を実装し、境界・回転・蓋・段位置テストおよび既存26ケースでPASSを確認。
- 混載では残数最多の高さ群だけでなく、積載可能な高さ群を候補として比較し、四隅の高さ・配置数・次段の余裕を評価する方式に変更。26ケースで配置合計が98箱増え、配置数減少なし、Supervisor全件PASSを確認。

### 2026-09-23

- **混載エンジン全面書き換え（MSP-EPハイブリッド）**: `boundary_min_short_side`（TP-342×16+TP-332×16=32個）が
  固定グリッド方式の隙間により6/32個しか配置できなかった問題を修正。Module-Aware Strip Packing
  （行分割＋FFD詰め）を主アルゴリズムとし、Extreme Points法で残渣充填する方式に変更。結果、32/32個を配置し
  最上段四隅高さ一致（`level_top_four_corners`、最上段のみ対象、各コーナー3.0mm以内）もPASS。
- **層内高さグルーピング追加**: 高さの異なる箱が同一層に混在し四隅不一致を起こす副作用を修正
  （`_choose_layer_height`）。
- **下段オーバーサイズ制約を正式化**: 直接支持する下段箱が上段箱より幅・奥行き両方とも1.0mmを超えて大きい場合の段積みを禁止
  （`_is_oversized_support` / `_has_oversized_support`）。既存の支持面積比率85%チェックに追加する形で適用し、
  `supervisor/validate.py` にも同等の独立検証項目を追加。
- 向き（回転）の一致を強制する制約は要件により追加していない。
- 上記変更後、全13テストケース（`tester/run_tests.py` / `supervisor/validate.py`）で回帰なし・全件PASSを確認。
