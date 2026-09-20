---
layout: page
title: 使用ガイド
---

# 使用ガイド

本ページでは、パレタイズ試作プロジェクトの基本的な使用方法と各種ツールの起動・操作方法を説明します。

## プロジェクト構成

パレタイズ試作プロジェクトは、以下の複数のサブエージェントと管理コンポーネントで構成されています：

```
palletizing_prototype/
├── develop/
│   ├── orchestrator/              # 全体統括
│   ├── box_research/              # 箱仕様調査・箱データベース
│   ├── algorithm_research/        # アルゴリズム方式調査
│   ├── test_programmer/           # テストデータ作成・テストケース管理
│   ├── algorithm_programmer/      # パレタイズアルゴリズム実装
│   ├── visualizer/                # 3D/2D可視化ツール
│   ├── tester/                    # テスト実行・シミュレーション
│   ├── supervisor/                # 制約検証・バリデーション
│   ├── constraints/               # 荷姿制約仕様
│   └── .github/instructions/      # 各エージェント指示書
├── main/                          # メインブランチ（リリース版）
├── gh-pages/                      # GitHub Pages（本ドキュメント）
└── README.md                      # プロジェクト概要
```

## エージェント構成と役割

### Orchestrator
- 他サブエージェントを統括する管理者
- ユーザーからの要望に応じて計画を立案
- プロジェクト全体の進行と整合性を管理

### Box Research
- 箱仕様（寸法、嵌合深さ、リブ厚み）の調査
- 箱データベース（`box_research/box_db.json`）の作成・管理
- TP規格コンテナおよび非TP規格箱の仕様整理

### Algorithm Research
- 嵌合・リブ構造に対応したパレタイズ手法の調査
- アルゴリズム方式の提案
- 参考資料：[`develop/algorithm_research/proposal.md`](https://github.com/TakahiroNakadaTMC/palletizing_prototype/blob/develop/algorithm_research/proposal.md)

### Test Programmer
- テスト用の箱リスト作成
- 単載・混載等のテストパターン設計
- テストケースJSON群の管理
- テストケースビューア提供

### Algorithm Programmer
- パレタイズアルゴリズムの実装
- TP規格モジュール嵌合ロジックの実装
- フィードバックをもとにプログラムの改良

### Visualizer
- アルゴリズム出力結果（配置座標、回転、積み順）の3D可視化
- ブラウザベースの3Dインタラクティブビューワ提供
- パレット仕様ガイドラインの描画

### Tester
- テスト箱リストでアルゴリズムを実行
- 荷山形成シミュレーション実施
- エラーログの記録と報告

### Supervisor
- `constraints/constraints.md` に基づき制約検証
- 出力された荷姿が制約を満たしているか監視
- 制約違反の具体的な問題点を報告
- 検証レポートの自動生成

## 基本的なワークフロー

### フェーズ 1: 要件定義・データ整備

1. ユーザーと対話形式で `constraints/constraints.md` を作成・確定
2. `box_research` が箱仕様を調査し、箱データベースを作成
3. `algorithm_research` がパレタイズ手法を調査・提案

### フェーズ 2: 実装・ツール作成

1. `test_programmer` がテストケースを作成
2. `algorithm_programmer` がアルゴリズムを実装
3. `visualizer` が可視化ツールを開発

### フェーズ 3: 実行・検証・改善ループ

1. `tester` がアルゴリズムを実行
2. `visualizer` で荷姿を確認
3. `supervisor` が制約検証
4. NGまたはエラーの場合は改善フィードバック
5. 合格するまでループ

---

## ツール使用方法

### 1. 3D/2D可視化ツール (visualizer)

パレタイズアルゴリズムの出力結果を3Dブラウザビューワで確認できます。

#### 1.1 統合ビューワサーバーの起動（推奨）

```bash
cd develop
python3 visualizer/serve_3d_viewer.py
```

**ブラウザアクセス**: `http://localhost:8082`

**機能**:
- プルダウンメニューで `tester/results/` 内の全テスト結果を切り替え表示
- リアルタイム3Dレンダリング（パレット・ガイドラインフレーム・箱・ラベル）
- タイムラインスライダーで積み上げ工程をステップ実行
- 自動再生機能（0.5x, 1x, 3x の再生速度指定可能）
- マウスドラッグで360度自由回転・パン・ズーム（OrbitControls）
- カメラプリセット（俯瞰 ISO、上面 Top、正面 Front、側面 Side）
- 箱クリック時に詳細情報表示：型番、座標 (X, Y, Z)、外寸、回転角、嵌合深さ、支持箱 Order 番号

#### 1.2 スタンドアロンHTML生成

単一のテスト結果をスタンドアロンHTMLとして生成することもできます：

```bash
cd develop
python3 visualizer/visualize.py test_programmer/test_cases/mixed_tp_same_height.json \
  -o visualizer/viewer.html
```

生成された `visualizer/viewer.html` をブラウザで直接開いて確認できます。

---

### 2. テストケース管理ツール (test_programmer)

テストケースの投入箱リストを確認・編集・作成できるWebビューワを提供します。

#### 2.1 テストケースビューアの起動

```bash
cd develop
python3 test_programmer/serve_testcase_viewer.py
```

**ブラウザアクセス**: `http://localhost:8083`

**機能**:
- 既存テストケースの一覧表示・確認
- 投入箱リスト（荷山構成）の可視化
- 個別箱型番の採用/解除
- 投入数量の変更
- 新規テストパターンの作成
- 一括保存機能

#### 2.2 テストケースの再生成

箱データベース（`box_research/box_db.json`）を更新した際は、以下を実行してテストケース全体を再生成できます：

```bash
cd develop
python3 test_programmer/generate_testcases.py
```

**生成されるテストケース例**:
- `single_tp332.json`: TP-332 単載（60個）
- `mixed_tp_same_height.json`: 同一高さ混載（42個）
- `mixed_tp_different_heights.json`: 異高混載（74個）
- `boundary_height_limit.json`: 高さ制約境界値テスト（48個）

---

### 3. アルゴリズム実行ツール (algorithm_programmer)

パレタイズアルゴリズムをCLIで実行し、シミュレーション結果を生成します。

#### 3.1 単一テストケースの実行

```bash
cd develop
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json
```

**出力例**:
```
Loaded 1 test case(s): mixed_tp_same_height
Test: mixed_tp_same_height (mixed, 42 boxes)
  Pattern: Mixed Packing (Extended EP + BFD)
  ...
  ✓ Result output: tester/results/result_mixed_tp_same_height.json
```

#### 3.2 結果をJSONファイルに出力

```bash
cd develop
python3 algorithm_programmer/cli.py test_programmer/test_cases/mixed_tp_same_height.json \
  -o tester/results/result_mixed_tp_same_height.json
```

**出力ファイル形式** (`result_*.json`):
```json
{
  "test_case": "mixed_tp_same_height",
  "algorithm": "HM-Palletizer",
  "boxes": [
    {
      "order": 1,
      "box_id": "box_001",
      "position": [100, 200, 50],
      "rotation": 0,
      "supported_by": []
    },
    ...
  ]
}
```

---

### 4. テスト実行・シミュレーション (tester)

全テストケースを一括実行し、シミュレーション結果を生成します。

#### 4.1 全テストの一括実行

```bash
cd develop
python3 tester/run_tests.py
```

**出力結果**:
- `tester/results/result_*.json`: 各テストケースのシミュレーション結果
- 以下の例が自動生成されます：
  - `result_single_tp332.json`
  - `result_mixed_tp_same_height.json`
  - `result_boundary_height_limit.json`
  - （計13テストケース分）

#### 4.2 結果の可視化

テスト完了後、visualizer で結果を確認できます：

```bash
cd develop
python3 visualizer/serve_3d_viewer.py
```

---

### 5. 制約検証ツール (supervisor)

パレタイズ結果が制約仕様を満たしているか自動検証します。

#### 5.1 バリデーション実行

```bash
cd develop
python3 supervisor/validate.py
```

**検証項目**:
1. **最大積載高さ制約** (≤ 1200 mm)
2. **長辺荷姿スパン制約** (< 1360 mm)
3. **短辺荷姿スパン制約** (800 mm ≤ Y < 1100 mm)
4. **天地固定・回転角度制約** (0° / 90° のみ)
5. **嵌合沈み込み計算** の正確性
6. **空中配置禁止・底面支持率** (≥ 85%)
7. **3D幾何衝突検出** （干渉 0 件）
8. **積み込み順序トポロジカル整合性** (下段優先)

#### 5.2 検証レポート確認

検証結果は以下に出力されます：

```
supervisor/
└── reports/
    └── validation_report.md
```

**レポート内容**:
- テストケースごとの合否判定
- 制約違反の詳細（該当箱、制約項目、違反値）
- 統計サマリー（合格率、平均充填率等）

---

### 6. 箱データベース管理 (box_research)

工業用TP規格コンテナおよび非TP規格箱の仕様情報を一元管理します。

#### 6.1 箱データベースビューアの起動

```bash
cd develop
python3 box_research/serve_viewer.py
```

**ブラウザアクセス**: `http://localhost:8081`

**機能**:
- 登録箱全体の一覧表示
- 各箱の寸法・嵌合深さ・リブ厚みを表示
- TP規格モジュール関係の可視化
- 互換性マトリックスの確認

#### 6.2 箱データベース形式

`box_research/box_db.json` の構造：

```json
{
  "boxes": [
    {
      "id": "TP-332",
      "name": "TP-332 標準型",
      "width": 335.0,
      "length": 335.0,
      "height": 195.0,
      "fitting_depth": 10.0,
      "rib_thickness": 22.0,
      "module_ratio": [1.0, 1.0],
      "series": "TP-330系"
    },
    ...
  ]
}
```

---

## ワークフロー例：シンプルな実行フロー

ここでは、既に構築されたプロジェクトでアルゴリズムテストを実行する基本フロー示します：

### ステップ1: アルゴリズムテストの実行

```bash
cd develop
python3 tester/run_tests.py
```

### ステップ2: ビジュアライゼーションの起動

```bash
# 別のターミナルで
cd develop
python3 visualizer/serve_3d_viewer.py
```

ブラウザで `http://localhost:8082` を開き、テスト結果を選択して3D表示を確認。

### ステップ3: 制約検証

```bash
# 別のターミナルで
cd develop
python3 supervisor/validate.py
```

ターミナルに検証結果が表示され、`supervisor/reports/validation_report.md` に詳細が記録されます。

### ステップ4: 結果レビュー

- **3D表示**: visualizer で荷積み状況を確認
- **詳細検証**: validation_report.md で制約充足状況を確認
- **改善判定**: NGの場合、algorithm_programmer にフィードバック

---

## データフォーマット

### 1. 箱データベース (`box_research/box_db.json`)

```json
{
  "boxes": [
    {
      "id": "TP-332",
      "name": "TP-332 標準型",
      "width": 335.0,
      "length": 335.0,
      "height": 195.0,
      "fitting_depth": 10.0,
      "rib_thickness": 22.0,
      "module_ratio": [1.0, 1.0],
      "series": "TP-330系",
      "characteristics": "基準モジュール標準高"
    }
  ],
  "pallet_spec": {
    "width": 1200.0,
    "length": 1000.0,
    "height": 144.0,
    "max_load_height": 1200.0,
    "max_overhang_long": 1360.0,
    "min_short_side": 800.0,
    "max_short_side": 1000.0
  }
}
```

**フィールド説明**:
- `id`: 箱型番
- `width`, `length`, `height`: 外寸 (mm)
- `fitting_depth`: 嵌合深さ (mm) - 上に積み上げた時に沈み込む深さ
- `rib_thickness`: 側面リブ厚み (mm)
- `module_ratio`: [幅方向モジュール比, 奥行方向モジュール比]
- `series`: TP規格シリーズ名
- `characteristics`: 型番の特性・用途

### 2. テストケース (`test_programmer/test_cases/*.json`)

```json
{
  "name": "mixed_tp_same_height",
  "description": "同一高さ（H=195mm）のモジュール平面組み合わせ混載",
  "type": "mixed",
  "boxes": [
    {
      "box_id": "TP-332",
      "quantity": 18
    },
    {
      "box_id": "TP-342",
      "quantity": 12
    },
    {
      "box_id": "TP-362",
      "quantity": 8
    },
    {
      "box_id": "TP-462",
      "quantity": 4
    }
  ],
  "total_boxes": 42
}
```

**フィールド説明**:
- `type`: "single" (単載) or "mixed" (混載)
- `boxes`: 投入する箱型番と数量のリスト
- `total_boxes`: 総箱数

### 3. パレタイズ結果 (`tester/results/result_*.json`)

```json
{
  "test_case": "mixed_tp_same_height",
  "algorithm": "HM-Palletizer",
  "pallet_spec": {
    "width": 1200.0,
    "length": 1000.0,
    "max_height": 1200.0
  },
  "boxes": [
    {
      "order": 1,
      "box_id": "TP-332",
      "position": [100, 200, 50],
      "rotation": 0,
      "external_size": {
        "width": 335.0,
        "length": 335.0,
        "height": 195.0
      },
      "supported_by": [],
      "timestamp": "2026-09-20T18:30:45Z"
    },
    {
      "order": 2,
      "box_id": "TP-342",
      "position": [435, 200, 50],
      "rotation": 0,
      "external_size": {
        "width": 503.0,
        "length": 335.0,
        "height": 195.0
      },
      "supported_by": [],
      "timestamp": "2026-09-20T18:30:46Z"
    },
    {
      "order": 3,
      "box_id": "TP-332",
      "position": [100, 535, 245],
      "rotation": 0,
      "external_size": {
        "width": 335.0,
        "length": 335.0,
        "height": 195.0
      },
      "supported_by": [1],
      "timestamp": "2026-09-20T18:30:47Z"
    }
  ],
  "summary": {
    "total_boxes": 42,
    "total_height": 1120,
    "fill_rate": 87.5,
    "layers": 6
  }
}
```

**フィールド説明**:
- `order`: 積み込み順序（1..N）
- `position`: [X, Y, Z] 座標 (mm)
- `rotation`: 回転角度（0 or 90 度のみ）
- `supported_by`: この箱を下から支持している箱の `order` のリスト
- `fill_rate`: パレット容積に対する占有率 (%)

### 4. 制約仕様 (`constraints/constraints.md`)

制約ファイルには、以下の項目が定義されます：

```markdown
## 1. パレット仕様
- 外寸: 1200 mm × 1000 mm
- 最大積載高: 1200 mm

## 2. 積載配置制約
- 長辺荷姿スパン: < 1360 mm
- 短辺荷姿スパン: 800 mm ≤ Y < 1100 mm
- 回転: 0° / 90° のみ（天地固定・横倒し禁止）

## 3. 嵌合・支持制約
- TP規格箱: 底面リブ構造により嵌合段積み可能
- 非TP規格箱: 同一型番の直上積み限定
- 底面支持率: ≥ 85%（空中浮き禁止）
- 衝突排除: 3D幾何干渉 0 件
```

---

## 実行環境と依存関係

### 必須環境
- **Python**: 3.8 以上
- **Node.js**: 14 以上（可視化ツール用）

### Pythonパッケージ
```bash
pip install numpy scipy matplotlib plotly jupyter
```

### Webブラウザ
- Chrome 90 以上
- Firefox 88 以上
- Safari 14 以上

---

## 参考資料

### 詳細ドキュメント

各エージェント・ツールの詳細は、以下を参照してください：

| 資料 | 内容 | パス |
| :--- | :--- | :--- |
| **箱仕様レポート** | TP規格体系、非TP規格箱仕様 | `develop/box_research/README.md` |
| **アルゴリズム提案** | パレタイズ手法の数学的背景 | `develop/algorithm_research/proposal.md` |
| **制約仕様** | 荷姿制約の詳細定義 | `develop/constraints/constraints.md` |
| **Visualizer仕様** | 3Dビューワの機能詳細 | `develop/visualizer/README.md` |
| **テスター仕様** | テスト実行フロー | `develop/tester/README.md` |
| **Supervisor仕様** | バリデーション項目詳細 | `develop/supervisor/README.md` |

### API リファレンス

**algorithm_programmer モジュール**:
```python
from algorithm_programmer.palletizer import HMPalletizer
from algorithm_programmer.models import BoxSpec, PalletSpec

# アルゴリズム初期化
palletizer = HMPalletizer(pallet_spec)

# 単載パレタイズ
result_single = palletizer.palletize_single(box_spec, num_boxes)

# 混載パレタイズ
result_mixed = palletizer.palletize_mixed(box_specs, quantities)
```

---

## トラブルシューティング

### Q1: ビューワが起動しない / ポート接続エラーが出る

**原因**: 別の処理がすでにポートを使用している。

**解決**:
```bash
# ポート確認
lsof -i :8082  # visualizer
lsof -i :8083  # test_programmer
lsof -i :8081  # box_research

# プロセス終了
kill -9 <PID>

# 別ポートで起動（例：9082）
python3 visualizer/serve_3d_viewer.py --port 9082
```

### Q2: テスト実行時に "box_db.json not found" エラー

**原因**: 作業ディレクトリが正しくない。

**解決**:
```bash
cd develop  # プロジェクトの develop ディレクトリに移動
python3 tester/run_tests.py
```

### Q3: 可視化ツールで箱が表示されない

**原因**: テスト結果ファイルが存在しない、または形式が異なる。

**解決**:
```bash
# テスト実行から始める
cd develop
python3 tester/run_tests.py

# その後ビューワを起動
python3 visualizer/serve_3d_viewer.py
```

### Q4: supervisor バリデーションで constraint violation が大量に出る

**原因**: アルゴリズムの実装にバグがある、または `constraints.md` と実装に齟齬がある。

**対応**:
1. `validation_report.md` で詳細な違反内容を確認
2. `visualizer` で3D表示を確認し、物理的に可能な配置か検証
3. algorithm_programmer に改善フィードバックを実施

---

## よくある質問（FAQ）

### TP規格モジュールとは？

TP（Toyota Plastic）規格は、自動車産業で標準化されたコンテナ規格です。基準モジュール（335 mm × 335 mm）の倍数・分数関係で異なる型番が設計されており、**底面のリブ構造により相互嵌合（スタッキング）が可能**です。

詳細は `develop/box_research/README.md` の「TP規格コンテナの体系」を参照。

### 嵌合深さ (fitting_depth) とは？

上に積み重ねた箱が下の箱に沈み込む深さです。例えば `fitting_depth = 10 mm` の場合、上の箱が下に最大10mm沈み込むため、段積み総高さは以下のように計算します：

$$H_{total} = H_{bottom} + \sum_{k=2}^N (H_k - fitting\_depth_k)$$

### 回転（rotation）は 0 と 90 以外で可能？

**いいえ**。制約仕様で天地固定・上下反転・横倒し禁止が定義されており、許可される回転は **0° または 90°** のみです。

### 短辺制約「800 mm ≤ Y < 1100 mm」の意味は？

パレット短辺（1000 mm）の制約として、荷姿が短辺方向に 800 mm 以上 1100 mm 未満（1000 mm はジャストフィット判定）でなければならないという意味です。これにより、パレット上で適切にセンタリングされた安定的な積載が実現します。

### テストケースを自分で作成できる？

はい。`test_programmer/serve_testcase_viewer.py` で Webビューワを起動し、UIから新規テストケースを作成・保存できます。

---

## サポート・貢献

### バグ報告

GitHub Issues で報告してください：
[Issues - TakahiroNakadaTMC/palletizing_prototype](https://github.com/TakahiroNakadaTMC/palletizing_prototype/issues)

### 改善提案

Pull Request で提案を送信してください。詳細は [CONTRIBUTING.md](https://github.com/TakahiroNakadaTMC/palletizing_prototype/blob/main/CONTRIBUTING.md) を参照。

---

**次のステップ**: [アルゴリズム説明](/palletizing_prototype/wiki/algorithm-explanation.html)を参照して技術詳細を確認してください。
