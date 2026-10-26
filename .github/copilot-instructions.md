# GitHub Copilot Instructions

<!-- markdownlint-configure-file { "MD013": { "tables": false } } -->

このドキュメントは、パレタイズアルゴリズム試作プロジェクト全体に対して GitHub Copilot が常時適用すべき開発規約、制約、ループエンジニアリング手順、およびコーディング規約を定義する。

詳細な仕様・制約については [`README.md`](../README.md) を参照。

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
| `python box_research/serve_viewer.py` | 箱・蓋DBビューア起動 | — | ブラウザで `http://localhost:8081` |
| `python3 test_programmer/generate_testcases.py` | テストケース生成 | `box_research/box_db.json` | `test_programmer/test_cases/*.json` |
| `python3 tester/run_tests.py` | 全テストケース実行 | `test_programmer/test_cases/` | `tester/results/result_*.json` |
| `python3 tester/run_tests.py -k single_tp332` | 特定テストを実行 | 名前パターン | 該当結果 |
| `python3 supervisor/validate.py` | 制約バリデーション | `tester/results/*.json` | `supervisor/reports/validation_report.md` |
| `python3 visualizer/visualize.py tester/results/result_*.json` | 3D可視化（スタンドアロンHTML生成） | 結果JSON | `visualizer/viewer.html` |
| `python3 visualizer/serve_3d_viewer.py` | 統合ビューワサーバー起動 | — | ブラウザで `http://localhost:8082` |

### Lid Database Management **[NEW: Phase 2]**

蓋データベースを管理するUIツール：

```bash
# サーバー起動
python box_research/serve_viewer.py

# ブラウザで以下のURLにアクセス:
# - 箱DBビューア: http://localhost:8081/box_db_viewer.html
# - 蓋DBビューア: http://localhost:8081/lid_db_viewer.html
```

**蓋DBビューアの機能**:

- 蓋一覧表示・追加・編集・削除
- 嵌め方（fit_type）の選択: 外嵌め / 内嵌め / なし
- 蓋仕様（寸法・厚み等）の管理
- サーバーへの永続化保存

**箱DBビューアの新機能**:

- 箱編集時に互換蓋（compatible_lids）をチェックボックスで選択
- 蓋を箱に紐付けて保存

### Quick Single-Test Validation

```bash
# 1. 単一テストケースのパレタイズ実行
python3 algorithm_programmer/cli.py \
  test_programmer/test_cases/single_tp332.json \
  -o tester/results/result_test.json

# 2. 結果を可視化
python3 visualizer/visualize.py tester/results/result_test.json -o visualizer/viewer_test.html

# 3. 制約検証
python3 supervisor/validate.py
```

---

## High-Level Architecture

### System Overview

```text
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

```text
test_programmer/test_cases/*.json
  ↓
tester/run_tests.py
  ├→ algorithm_programmer/palletizer.py（嵌合・配置計算）
  └→ tester/results/result_*.json（パレタイズ結果）
  
tester/results/result_*.json
  ├→ visualizer/visualize.py（3D描画）→ visualizer/*.html
  └→ supervisor/validate.py
    ├→ 10 constraint checks (積載高さ、荷姿幅、四隅高さ、段積みサイズ、嵌合整合性、干渉検出等)
    └→ supervisor/reports/validation_report.md（PASS/NG判定）

[検証結果がNG] → algorithm-programmer に改善指示 → palletizer.py修正 → ループ再開
[検証結果がOK] → 次テストケースへ
```

### Key Algorithms & Logic

#### **palletizer.py** (パレタイズ計算エンジン)

1. **単載エンジン (`palletize_single`)**
   - 0度/90度グリッド + スプリット（レンガ）分割パターンを自動生成・比較
   - 長辺荷姿幅 $800\text{ mm} \le X_{span} < 1360\text{ mm}$、
     短辺荷姿幅 $800\text{ mm} \le Y_{span} < 1100\text{ mm}$ の境界フィルタリング
   - `fitting_depth` を考慮した最大段数・Z座標計算
   - 偶数/奇数段の反転によるインターロッキング（荷崩れ防止）

2. **混載エンジン (`palletize_mixed`)**
   - 拡張 Extreme Points (EP) 法 ＋ Best-Fit Decreasing 配置
   - 嵌合Z座標ソルバー: `Z = max(Z_top of support - fitting_depth)`
   - 支持面判定: 広面積85%以上が接地（空中浮き排除）
   - TP規格モジュール嵌合ボーナス・境界ペナルティ付き多目的評価関数

3. **積み順決定 (`assign_loading_orders`)**
   - トポロジカルソート (Z昇順 → Y昇順 → X昇順)
   - 下段優先・干渉フリーな `order` (1..N) 付番
   - `supported_by` (支持下段箱リスト) を記録

#### **validate.py** (制約バリデータ)

12個の厳格なチェック項目 (詳細は [constraints/constraints.md](../constraints/constraints.md)):

1. 積載全高 ≤ 1200mm
2. 長辺荷姿幅 $800\text{ mm} \le X_{span} < 1360\text{ mm}$
3. 短辺荷姿幅 $800\text{ mm} \le Y_{span} < 1100\text{ mm}$
4. 方向別はみ出し（全段・蓋込みで片側20mm以下、X/Y別設定。投入単載の箱本体底面辺が670mm以上となる方向のみ例外）
5. 最高層四隅高さ一致 (各コーナーの誤差 3.0mm以内)
6. 3D干渉検出（嵌合沈み込みを許容）
7. 嵌合・段積み整合性
8. 広面支持率 ≥85%
9. 下段支持箱サイズ制限（幅・奥行きの両方が上段箱より1.0mmを超えて大きい直接支持箱は禁止）
10. 回転角度 0° or 90° のみ
11. 積み順トポロジカル整合性
12. 荷姿センタリング（箱・蓋外形の外接矩形中心とパレット中心が各方向0.01mm以内で一致）

---

## Key Conventions & Patterns

寸法の表示・記載順は **L × W × H（長手方向 × 短手方向 × 高さ）** に統一する。
箱・蓋DBでは `length` がL、`width` がW。
配置結果の `width` / `length` は回転後のX/Y寸法であり、
表示時に長辺をL、短辺をWとする。既存キーと座標の意味、保存値は変更しない。

### Data Schemas

#### Box Database (`box_research/box_db.json`)

```json
{
  "boxes": [
    {
      "id": "TP-332",
      "name": "TP-330系 (335×335×195)",
      "type": "TP",
      "length": 335,
      "width": 335,
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
  "pallet": {"length": 1200, "width": 1000, "max_height": 1200},
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
  def calculate_max_layers(
      height: float, fitting_depth: float, max_height: float
  ) -> int:
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
- **最高層四隅**: 各コーナーの高さ誤差 3.0mm以内で一致（安定性確保）

#### ⚠️ Fitting Logic

- **Z座標計算**: `Z_upper = Z_lower + H_lower - fitting_depth`
- **嵌合沈み込み許容**: 3D衝突判定時に `fitting_depth` ぶん沈み込んだ状態を正常と判定
- **TP規格**: モジュール倍数関係にある箱同士の嵌合段積みが許可される
- **外嵌め蓋付きTP箱**: 積み方の判定上はコラム積み限定。同一蓋IDで箱・蓋外形の位置と範囲を揃えれば、箱IDが異なるTP箱同士も積載可能
- **非TP規格**: 同一型番のコラム積みのみ許可

#### 📏 Boundary Rules

- **長辺**: 荷姿の長辺方向スパン $800\text{ mm} \le X_{span} < 1360\text{ mm}$
- **短辺**: 荷姿の短辺方向スパン $800\text{ mm} \le Y_{span} < 1100\text{ mm}$
- **方向別はみ出し**: 全段・箱と蓋の外形の片側はみ出しをX/Y別の設定値以下とする
  （`max_overhang_x_mm` / `max_overhang_y_mm`、既定各20mm、境界値を含む）。
  投入時に同一箱型番・同一蓋条件の単載で、回転後の箱本体底面辺が670mm以上となる方向のみ通常制限を免除する。
  例外でも荷姿幅上限は維持する。結果の `input_box_variants` で投入種類を記録し、
  未配置により1種類になった混載には例外を適用しない。旧30mm制限・旧設定項目は廃止。
- **荷姿センタリング**: 箱・蓋外形の外接矩形中心をパレット中心に合わせる（各方向の誤差0.01mm以内）
- **支持率**: 箱の底面積の85%以上がパレット/下段箱に接地（空中浮きを排除）

---

## Repository References

- **[README.md](../README.md)** — GitHub Copilot 版プロジェクト構成・ルール・エージェント役割定義
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
- ✅ README.md への参照を明確化
