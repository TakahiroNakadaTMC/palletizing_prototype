---
layout: page
title: 使用ガイド
permalink: /wiki/user-guide/
---

# 使用ガイド

本ページでは、パレタイズ試作プロジェクトの基本的な使用方法と各種ツールの起動・操作方法を説明します。

## プロジェクト構成

パレタイズ試作プロジェクトは、以下の複数のサブエージェントと管理コンポーネントで構成されています：

```
palletizing_prototype/
├── .agent/                        # エージェント設定ファイル
│   ├── orchestrator.yaml          # 統括管理者
│   ├── box-research.yaml          # 箱仕様調査
│   ├── algorithm-research.yaml    # アルゴリズム調査
│   ├── test-programmer.yaml       # テストケース作成
│   ├── algorithm-programmer.yaml  # アルゴリズム実装
│   ├── visualizer.yaml            # 可視化ツール
│   ├── tester.yaml                # テスト実行
│   └── supervisor.yaml            # バリデーション
├── box_research/                  # 箱仕様調査・箱データベース
├── algorithm_research/            # アルゴリズム方式調査
├── test_programmer/               # テストデータ作成・テストケース管理
├── algorithm_programmer/          # パレタイズアルゴリズム実装
├── visualizer/                    # 3D/2D可視化ツール
├── tester/                        # テスト実行・シミュレーション
├── supervisor/                    # 制約検証・バリデーション
├── constraints/                   # 荷姿制約仕様
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
3. **【ユーザーレビュー】** ユーザーが `box_research/box_db.json` を確認し、不足している箱情報を追加・変更
4. `algorithm_research` がパレタイズ手法を調査・提案

### フェーズ 2: 実装・ツール作成

1. `test_programmer` がテストケースを作成
2. **【ユーザーレビュー】** ユーザーが `test_programmer/test_cases/` のテストケースを確認し、不足しているテストパターンを追加・変更
3. `algorithm_programmer` がアルゴリズムを実装
4. `visualizer` が可視化ツールを開発

### フェーズ 3: 実行・検証・改善ループ

1. `tester` がアルゴリズムを実行
2. `visualizer` で荷姿を確認
3. **【ユーザー結果確認】** ユーザーがテスト結果を確認し、荷姿の妥当性を検証
4. `supervisor` が制約検証
5. **【ユーザー荷姿レビュー】** ユーザーが荷姿に関するレビューをフィードバック（改善提案、制約違反の指摘等）
6. `algorithm_programmer` がレビューに基づいてアルゴリズムを修正
7. NGまたはエラーの場合は **フェーズ 3 のステップ 1 に戻る** ループ

## ユーザーレビューのポイント

### フェーズ 1: 箱データベース確認

`box_research/box_db.json` を確認する際のチェックポイント：

- **必須項目の完全性**: すべての箱に `id`, `name`, `type`, `width`, `length`, `height`, `fitting_depth`, `rib_thickness` が定義されているか
- **寸法の正確性**: 実物の仕様書と照合し、寸法値が正確か
- **TP規格の正確性**: `module_ratio` が正しく定義されているか（例: 330系は `1x1`, 460系は `2x1`）
- **不足箱の追加**: プロジェクト対象の箱で未登録のものがあれば追加

**修正方法**: `box_research/box_db.json` を直接編集してから、`box_research` エージェントに修正を反映させます。

### フェーズ 2: テストケース確認

`test_programmer/test_cases/` のテストケースを確認する際のチェックポイント：

- **テストパターンの網羅性**: 単載、混載、境界値等の主要なパターンが含まれているか
- **投入箱数の妥当性**: 実運用に近い数量設定になっているか
- **不足テストパターンの追加**: 検証したいシナリオで未カバーのパターンがあれば追加
- **パレット仕様**: テストケースのパレット寸法が実運用に合致しているか

**修正方法**: 以下のいずれかの方法で修正します：
- テストケースJSON を直接編集
- `test_programmer/serve_testcase_viewer.py` を起動し、ウェブUIで編集・作成

### フェーズ 3: テスト結果確認

テスト実行後、以下の手順でユーザーが結果を確認します：

1. **可視化ツール確認**: `visualizer/serve_3d_viewer.py` でアルゴリズムの出力結果を3D確認
   - 箱配置の効率性を確認
   - 積み上げ工程が物理的に妥当か検証
   - 嵌合・リブ構造が正しく考慮されているか確認

2. **制約検証結果確認**: `supervisor/reports/validation_report.md` で制約違反の有無を確認
   - 積載高さ制約を満たしているか
   - 長辺・短辺制約を満たしているか
   - 同箱コラム積み等の特殊制約を満たしているか

3. **レビューフィードバック**: 以下の内容を含めてアルゴリズム改善提案を行う
   - 効率性の問題：スペース利用率の改善案
   - 安定性の問題：積み上げ安定性の懸念点
   - 制約違反：制約を満たしていない具体的な箇所
   - その他の実運用上の懸念点

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

#### 1.3 可視化ツールでのユーザーレビュー操作ガイド

可視化ツール（統合ビューワまたはスタンドアロンHTML）を使用して、アルゴリズムの出力結果をレビューする具体的な手順を説明します。

##### ステップ1: ビューワの起動と結果の読み込み

**統合ビューワの場合**:
```bash
cd develop
python3 visualizer/serve_3d_viewer.py
```
その後、`http://localhost:8082` をブラウザで開きます。

**スタンドアロンHTMLの場合**:
```bash
cd develop
python3 visualizer/visualize.py tester/results/result_mixed_tp_same_height.json \
  -o visualizer/viewer.html
```
生成された `visualizer/viewer.html` をブラウザで直接開きます。

##### ステップ2: 結果データの確認

1. **テスト基本情報**: 画面左上のパネルで以下を確認
   - テスト名とテストパターン
   - 投入箱の総数と総重量
   - パレット寸法（横 X × 奥行 Y × 高さ Z）
   - アルゴリズムの実行時間
   - エラーまたは警告の有無

2. **統計情報**: 画面上部の統計パネルで以下を確認
   - スペース利用率（%）
   - 積載高さ（cm）
   - 積み上げ段数
   - 箱配置の安定性スコア

##### ステップ3: 3D表示での視覚検証

1. **カメラプリセットの使用**
   - **ISO View（俯瞰）**: 全体像を把握、パレット面での分布確認
   - **Top View（上面）**: パレット面上での箱配置パターンを確認
   - **Front View（正面）**: 前面からの積み上げ工程を確認
   - **Side View（側面）**: 側面からの積み上げ工程と高さバランスを確認

2. **マウス操作による詳細確認**
   - **左ドラッグ**: 自由に360度回転
   - **右ドラッグ（またはShift+ドラッグ）**: パン（移動）
   - **ホイール**: ズーム（拡大・縮小）
   - **ダブルクリック**: 指定座標に焦点を移動

##### ステップ4: 箱情報の詳細確認

1. **箱クリックによる詳細情報表示**
   - 3D表示内の任意の箱をクリック
   - 右側パネルに以下の情報が表示:
     - 箱型番（例: TP-332）
     - 配置座標 (X, Y, Z) [mm]
     - 外寸（幅 × 奥行 × 高さ）[mm]
     - 回転角（0° または 90°）
     - 嵌合深さ [mm]
     - 支持箱の Order 番号
     - 荷重状況（支持している箱の総数と重量）

2. **積み上げ順序の確認**
   - 画面下のタイムラインスライダーで積み上げ工程をステップ実行
   - または「自動再生」ボタンで再生速度を指定して再生（0.5x, 1x, 3x）
   - 各ステップで箱をクリックして配置情報を確認

##### ステップ5: 箱配置パターンの妥当性検証

1. **効率性の確認**
   - パレット面の利用効率が良好か（面利用率 > 85% が目安）
   - 空間の無駄が最小化されているか
   - 同じ型番の箱が効率的にグループ化されているか

2. **安定性の確認**
   - 箱が不安定に積み上がっていないか
   - 下段の箱が上段の箱の重量をバランスよく支持しているか
   - 積み上げ工程に不合理な順序がないか（下から上への積み重ね等）

3. **嵌合・リブ構造の確認**
   - TP規格の嵌合がデザイン通りに機能しているか
   - リブ厚みの制約が遵守されているか
   - 混載時に異なる箱型が互いに適切に支持できているか

4. **制約遵守の確認**
   - 積載高さが制約範囲内か（例: 1500〜2000 mm）
   - 短辺方向の配置が制約を満たしているか（例: 800〜1100 mm）
   - その他の特殊制約（同箱コラム積み等）が守られているか

##### ステップ6: レビューコメントの記録

問題点や改善提案を発見した場合は、以下の形式でレビューフィードバックを記録します：

```markdown
## レビュー結果: [テスト名]
日時: [実施日時]
実施者: [ユーザー名]

### 確認内容
- ✓ スペース利用率: [実測値] %
- ✓ 積載高さ: [実測値] cm
- ✓ 安定性スコア: [実測値]

### 問題点
1. [問題の詳細説明]
   - 影響度: [高/中/低]
   - 具体的な場所: [箱型番、Order番号 等]
   
### 改善提案
1. [提案内容]
2. [提案内容]

### 制約検証結果
- 積載高さ制約: [合否]
- 短辺制約: [合否]
- その他: [合否]
```

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

#### 2.1.1 テストケースビューアでのユーザー操作ガイド

##### ステップ1: テストケースの読み込みと確認

1. ビューワを起動すると、`test_programmer/test_cases/` 内の全テストケースが一覧表示されます
2. 確認したいテストケースをクリックして詳細を表示
3. 以下の情報をレビューします：
   - テスト名とテストタイプ（単載/混載等）
   - パレット仕様
   - 投入箱リスト（型番、数量、合計）
   - 期待される総重量と積載数量

##### ステップ2: 投入箱リストの確認・編集

1. **箱型番の採用/解除**
   - 左パネルの「箱リスト」で各箱型番の横にある チェックボックス をチェック/アンチェック
   - チェック状態を変更すると、右側の「投入数量」フィールドが有効/無効に切り替わります

2. **投入数量の変更**
   - 各箱型番の「投入数量」フィールドに数値を入力
   - リアルタイムで合計重量と総箱数が更新されます

3. **荷山構成の可視化**
   - 中央パネルで投入箱の組成を可視化（箱型番ごとの色分け）
   - 投入数量の変更時に動的に更新

##### ステップ3: 新規テストパターンの作成

1. **テストパターンの新規作成**
   - 画面下の「新規テストパターン作成」ボタンをクリック
   - テストパターン名（例: `custom_high_performance`）を入力
   - テストタイプ（単載/混載/異高混載等）を選択

2. **投入箱リストの定義**
   - 利用可能な箱型番の一覧から、使用する箱型番をチェック
   - 各箱型番の投入数量を設定
   - 「リセット」ボタンで入力を全クリアすることも可能

3. **パレット仕様の確認**
   - パレット寸法（横 × 奥行 × 高さ）が実運用に合致しているか確認
   - 必要に応じて変更

4. **保存**
   - 「保存」ボタンをクリック
   - 新しいテストケースJSON が `test_programmer/test_cases/` に保存されます

##### ステップ4: 既存テストケースの修正

1. **テストケースの読み込み**
   - テストケース一覧から修正対象のテストをクリック

2. **投入箱リストの修正**
   - 必要な箱型番を追加・削除：チェックボックスで制御
   - 各箱型番の投入数量を修正：数値を変更

3. **修正内容の確認**
   - 左上の「修正内容」パネルで変更差分を確認
   - 合計重量と総箱数の変化を確認

4. **保存**
   - 「保存」ボタンをクリックして修正を確定
   - または「キャンセル」で修正を破棄

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

#### 6.1.1 箱データベースビューアでのユーザー操作ガイド

##### ステップ1: データベースビューアの起動

```bash
cd develop
python3 box_research/serve_viewer.py
```

ブラウザで `http://localhost:8081` にアクセスします。

##### ステップ2: 登録箱の確認

1. **箱一覧の表示**
   - 左パネルに登録済みのすべての箱が表示されます
   - 箱型番、外寸（WxLxH）、型式別に整理されています

2. **各箱の詳細情報確認**
   - 箱をクリックすると、右パネルに以下の詳細が表示：
     - 箱ID と箱型番
     - 外寸（幅 × 奥行 × 高さ）[mm]
     - 嵌合深さ [mm]
     - リブ厚み [mm]
     - TP規格モジュール（例: 330系は 1x1, 460系は 2x1）
     - 箱重量（空重） [kg]
     - 材質・耐荷重等の補足情報

##### ステップ3: 箱情報の追加・編集

1. **新規箱の追加**
   - 画面下の「新規箱追加」ボタンをクリック
   - 以下の情報を入力：
     - 箱型番（例: `TP-332-A`）
     - 外寸：幅 [mm]、奥行 [mm]、高さ [mm]
     - 嵌合深さ [mm]
     - リブ厚み [mm]
     - TP規格モジュール（1x1, 2x1, 2x2 等）
     - 箱重量（空重） [kg]
   - 「保存」ボタンをクリック

2. **既存箱情報の修正**
   - 修正対象の箱をクリック
   - 右パネルの「編集」ボタンをクリック
   - 修正が必要な項目を更新
   - 「保存」ボタンをクリック

3. **箱の削除**
   - 削除対象の箱をクリック
   - 「削除」ボタンをクリック
   - 確認ダイアログで「削除」を選択

##### ステップ4: 互換性マトリックスの確認

1. **TP規格モジュール互換性の確認**
   - 画面上部の「互換性マトリックス」タブをクリック
   - 異なるモジュール規格の箱間の嵌合可能性を確認
   - 嵌合深さの差異による積み重ね制約を確認

2. **混載可能性の確認**
   - 「混載テスト」パネルで、複数箱型番の組み合わせを選択
   - これらの箱が混載可能か自動判定
   - 嵌合条件を満たすかどうかをリアルタイムで表示

##### ステップ5: 箱データベースのエクスポート・バックアップ

1. **JSON形式でのエクスポート**
   - 画面右上の「エクスポート」ボタンをクリック
   - `box_db.json` として保存されます
   - テスト環境への複製やバージョン管理に使用

2. **CSV形式での出力**
   - 「CSV出力」ボタンをクリック
   - Excel等での二次加工が可能

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

### Q3.1: 3D ビューワで回転・ズームが動作しない

**原因**: ブラウザのWebGL対応状態に問題がある、またはJavaScriptが無効化されている。

**解決**:
1. JavaScript が有効になっているか確認
2. WebGL対応ブラウザに切り替え（Chrome、Firefox、Safari最新版）
3. ブラウザキャッシュをクリア：Ctrl+Shift+Delete
4. `about:gpu` (Chrome) または `about:support` (Firefox) でGPU情報を確認
5. スタンドアロンHTML版を試す：
   ```bash
   python3 visualizer/visualize.py tester/results/result_*.json -o viewer.html
   ```

### Q3.2: タイムラインスライダーが反応しない

**原因**: JavaScriptイベントリスナーが未登録、またはブラウザ互換性の問題。

**解決**:
1. ブラウザのコンソールでエラーを確認（F12 → Console タブ）
2. 別ブラウザで試す
3. ブラウザを再起動
4. 統合ビューワをリロード：F5 キー

### Q3.3: 箱情報パネルが表示されない

**原因**: 3D表示の初期化が完了していない、またはクリックが正しく検出されていない。

**解決**:
1. ページの読み込みを待つ（ビューワの読み込み進捗表示を確認）
2. 3D表示エリアをクリックしてフォーカスを当てる
3. 別の箱をクリックしてみる（クリックターゲットの問題を確認）
4. ブラウザ再読み込み：F5

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

### 可視化ツールで複数の結果を比較できる？

はい。統合ビューワ (`visualizer/serve_3d_viewer.py`) では、プルダウンメニューで複数の結果を切り替えながら確認できます。複数ウィンドウで異なる結果を同時表示することも可能です：

```bash
# ウィンドウ1で統合ビューワを起動
python3 visualizer/serve_3d_viewer.py

# ウィンドウ2でスタンドアロンHTMLを開く
python3 visualizer/visualize.py tester/results/result_mixed_tp_same_height.json -o viewer1.html
# ブラウザで viewer1.html を開く

# ウィンドウ3でもう一つの結果を表示
python3 visualizer/visualize.py tester/results/result_mixed_tp_different_heights.json -o viewer2.html
# ブラウザで viewer2.html を開く
```

### 3D ビューワで特定の箱を強調表示できる？

箱情報パネルに表示される「Order番号」を使用してフィルタリングできます。特定の Order 番号をクリックすると、その箱に関連する支持・被支持関係が強調表示されます。これにより、複数層にわたる積み上げ構造を追跡できます。

### レビュー結果をレポートとして保存できる？

ブラウザの「印刷」機能（Ctrl+P または Cmd+P）で PDF として保存できます。以下の情報が含まれます：
- テスト名・実行日時
- テスト統計（投入箱数、総重量、スペース利用率等）
- 各箱の詳細配置情報
- キャプチャ時点での3D表示

レビュー結果を構造化された形式で記録する場合は、前述の「レビューコメント記録テンプレート」を使用してください。

---

## サポート・貢献

### バグ報告

GitHub Issues で報告してください：
[Issues - TakahiroNakadaTMC/palletizing_prototype](https://github.com/TakahiroNakadaTMC/palletizing_prototype/issues)

### 改善提案

Pull Request で提案を送信してください。詳細は [CONTRIBUTING.md](https://github.com/TakahiroNakadaTMC/palletizing_prototype/blob/main/CONTRIBUTING.md) を参照。

---

**次のステップ**: [アルゴリズム説明](/palletizing_prototype/wiki/algorithm-explanation.html)を参照して技術詳細を確認してください。
