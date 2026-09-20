# GitHub Copilot Instructions

このドキュメントは、パレタイズアルゴリズム試作プロジェクト全体に対して GitHub Copilot が常時適用すべき開発規約、制約、ループエンジニアリング手順、およびコーディング規約を定義する。

詳細な仕様・制約については [`GEMINI.md`](../GEMINI.md) を参照。

---

## Build, Test & Validation

### Running the Full Loop

```bash
# 全フェーズ一括実行（テスト生成→テスト実行→検証→可視化）
./scripts/run_loop_cycle.sh
```

実行時間: 約2～5分（テストケース数・アルゴリズムの複雑さに依存）

### Individual Commands

| コマンド | 説明 | 入力 | 出力 |
|---------|------|------|------|
| `python3 test_programmer/generate_testcases.py` | テストケース生成 | `box_research/box_db.json` | `test_programmer/test_cases/*.json` |
| `python3 tester/run_tests.py` | 全テストケース実行 | `test_programmer/test_cases/` | `tester/results/result_*.json` |
| `python3 tester/run_tests.py -k single_tp332` | 特定テストを実行 | 名前パターン | 該当結果 |
| `python3 supervisor/validate.py` | 制約バリデーション | `tester/results/*.json` | `supervisor/reports/validation_report.md` |
| `python3 visualizer/visualize.py tester/results/result_*.json` | 3D可視化（スタンドアロンHTML生成） | 結果JSON | `visualizer/viewer.html` |
| `python3 visualizer/serve_3d_viewer.py` | 統合ビューワサーバー起動 | — | ブラウザで `http://localhost:8082` |

### Quick Single-Test Validation

```bash
# 1. 単一テストケースのパレタイズ実行
python3 algorithm_programmer/cli.py test_programmer/test_cases/single_tp332.json -o tester/results/result_test.json

# 2. 結果を可視化
python3 visualizer/visualize.py tester/results/result_test.json -o visualizer/viewer_test.html

# 3. 制約検証
python3 supervisor/validate.py
```

---

## High-Level Architecture

### System Overview

```
【入力層】
  - box_research/box_db.json          ← 箱仕様DB（寸法・嵌合深さ・リブ）
  - test_programmer/test_cases/       ← テストケース群（投入箱リスト）
  - constraints/constraints.md        ← 荷姿制約仕様

【処理層】
  - algorithm_programmer/
    ├─ models.py                      ← データクラス (BoxSpec, PlacedBox, PalletSpec)
    ├─ palletizer.py                  ← パレタイズ計算エンジン (HM-Palletizer)
    └─ cli.py                         ← CLI実行インターフェース
  
  - tester/run_tests.py               ← テスト一括実行
  - supervisor/validate.py            ← 制約バリデーション

【出力・可視化層】
  - tester/results/result_*.json      ← パレタイズ結果（配置座標・積み順）
  - supervisor/reports/               ← 検証レポート
  - visualizer/                       ← 3D/2D可視化ツール
```

### Data Flow: Phase 3 Loop (Run-Validate-Improve)

```
test_programmer/test_cases/*.json
  ↓
tester/run_tests.py
  ├→ algorithm_programmer/palletizer.py（嵌合・配置計算）
  └→ tester/results/result_*.json（パレタイズ結果）
  
tester/results/result_*.json
  ├→ visualizer/visualize.py（3D描画）→ visualizer/*.html
  └→ supervisor/validate.py
    ├→ 9 constraint checks (積載高さ、長辺/短辺寸法、嵌合整合性、干渉検出等)
    └→ supervisor/reports/validation_report.md（PASS/NG判定）

[検証結果がNG] → algorithm-programmer に改善指示 → palletizer.py修正 → ループ再開
[検証結果がOK] → 次テストケースへ
```

### Key Algorithms & Logic

#### **palletizer.py** (パレタイズ計算エンジン)

1. **単載エンジン (`palletize_single`)**
   - 0度/90度グリッド + スプリット（レンガ）分割パターンを自動生成・比較
   - 長辺 <1360mm、短辺 800～1000mm の境界フィルタリング
   - `fitting_depth` を考慮した最大段数・Z座標計算
   - 偶数/奇数段の反転によるインターロッキング（荷崩れ防止）

2. **混載エンジン (`palletize_mixed`)**
   - 拡張 Extreme Points (EP) 法 ＋ Best-Fit Decreasing 配置
   - 嵌合Z座標ソルバー: `Z = max(Z_top of support - fitting_depth)`
   - 支持面判定: 底面積85%以上が接地（空中浮き排除）
   - TP規格モジュール嵌合ボーナス・境界ペナルティ付き多目的評価関数

3. **積み順決定 (`assign_loading_orders`)**
   - トポロジカルソート (Z昇順 → Y昇順 → X昇順)
   - 下段優先・干渉フリーな `order` (1..N) 付番
   - `supported_by` (支持下段箱リスト) を記録

#### **validate.py** (制約バリデータ)

9つの厳格なチェック項目 (詳細は [section 5 of GEMINI.md](../GEMINI.md)):
1. 積載全高 ≤ 1200mm
2. 長辺荷姿 < 1360mm
3. 短辺荷姿 800～1100mm
4. 最高層四隅高さ一致 (誤差 ±1.0mm以内)
5. 3D干渉検出（嵌合沈み込みを許容）
6. 嵌合・段積み整合性
7. 底面支持率 ≥85%
8. 回転角度 0° or 90° のみ
9. 積み順トポロジカル整合性

---

## Key Conventions & Patterns

### Data Schemas

#### Box Database (`box_research/box_db.json`)

```json
{
  "boxes": [
    {
      "id": "TP-332",
      "name": "TP-330系 (335×335×195)",
      "type": "TP",
      "width": 335,
      "length": 335,
      "height": 195,
      "fitting_depth": 10,
      "rib_thickness": 22,
      "module_ratio": "1x1",
      "description": "基準モジュール"
    }
  ]
}
```

#### Palletize Result (`tester/results/result_*.json`)

```json
{
  "test_name": "single_tp332",
  "pallet": {"width": 1200, "length": 1000, "max_height": 1200},
  "input_boxes": [...],
  "result": [
    {
      "order": 1,
      "box_id": "TP-332",
      "position": {"x": 0, "y": 0, "z": 0},
      "rotation": 0,
      "width": 335, "length": 335, "height": 195,
      "fitting_depth": 10,
      "supported_by": null
    }
  ],
  "summary": {
    "total_boxes": 60,
    "max_height": 1120,
    "loadable_footprint": {...}
  }
}
```

### Naming Conventions

- **関数・変数**: `snake_case` (例: `calculate_max_layers`, `placed_boxes`)
- **クラス**: `PascalCase` (例: `PlacedBox`, `PalletSpec`)
- **定数**: `UPPER_SNAKE_CASE` (例: `MAX_HEIGHT_MM`, `PALLET_WIDTH_MM`)
- **テストファイル**: `*_test.py`
- **テストケース名**: `{single|mixed|boundary}_{category}_{suffix}.json`

### Python Code Style

- **Python 3.8+** をターゲット
- **型ヒント**: `from typing import List, Dict, Optional, Tuple` で明示的に記述
- **Dataclass**: `models.py` でデータ構造を定義（`@dataclass`）
- **ドキュメント**: Google形式 docstring の使用
  ```python
  def calculate_max_layers(height: float, fitting_depth: float, max_height: float) -> int:
      """嵌合沈み込みを考慮した最大積載段数を算出
      
      Args:
          height: 箱の高さ [mm]
          fitting_depth: 嵌合沈み込み深さ [mm]
          max_height: パレット最大積載高さ [mm]
      
      Returns:
          最大積載段数
      """
  ```

### Directory Structure & Ownership

各エージェントが管理する独立領域（**破壊的変更を避ける**）:

- **`box_research/`** → box-research エージェントが箱仕様を調査・DB化
- **`algorithm_research/`** → algorithm-research が方式を提案
- **`test_programmer/`** → test-programmer がテストケースを生成
- **`algorithm_programmer/`** → algorithm-programmer がパレタイズエンジンを実装
- **`visualizer/`** → visualizer が3D/2D可視化ツールを開発
- **`tester/`** → tester がテスト実行・結果を管理
- **`supervisor/`** → supervisor が制約検証を実行
- **`constraints/`** → constraints.md（荷姿仕様書）は orchestrator と協議で策定

### Critical Constraints

#### 🚫 Absolute Limits

- **積載高さ**: 1200mm を **絶対に超えない** (物理的上限)
- **回転角**: 0° または 90° のみ（45°等は禁止）
- **上下反転**: 禁止（天地固定）
- **最高層四隅**: 誤差 ±1.0mm以内で高さ一致（安定性確保）

#### ⚠️ Fitting Logic

- **Z座標計算**: `Z_upper = Z_lower + H_lower - fitting_depth`
- **嵌合沈み込み許容**: 3D衝突判定時に `fitting_depth` ぶん沈み込んだ状態を正常と判定
- **TP規格**: モジュール倍数関係にある箱同士の嵌合段積みが許可される
- **非TP規格**: 同一型番のコラム積みのみ許可

#### 📏 Boundary Rules

- **長辺**: パレット長辺 1200mm に対して、荷姿の長辺方向スパン < 1360mm（160mmオーバーハング許容）
- **短辺**: パレット短辺 1000mm に対して、荷姿の短辺方向スパン 800～1100mm（安定性要件で下限800mm）
- **支持率**: 箱の底面積の85%以上がパレット/下段箱に接地（空中浮きを排除）

---

## Repository References

- **[GEMINI.md](../GEMINI.md)** — 詳細な仕様・ルール・エージェント役割定義
- **[constraints/constraints.md](../constraints/constraints.md)** — 荷姿制約仕様書
- **[.agent/README.md](../.agent/README.md)** — エージェント設定ファイル
- **[.github/prompts/](../github/prompts/)** — 各ロール別プロンプト群

---

**バージョン**: 2.0  
**作成日**: 2026-09-20  
**最終更新**: 2026-09-20

**主な改善点**:
- ✅ Build/test/lint コマンド（全フェーズループ・個別実行）を追加
- ✅ Single-test 実行フロー例を追加
- ✅ 高レベルアーキテクチャと data flow を図解
- ✅ Key algorithms（単載/混載エンジン、制約検証）の説明を簡潔にまとめた
- ✅ Data schema, naming conventions, Python style を実装ベースで具体化
- ✅ Critical constraints（絶対制約）と boundary rules を可視化
- ✅ GEMINI.md への参照を明確化
