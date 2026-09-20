---
layout: page
title: 使用ガイド
---

# 使用ガイド

本ページでは、パレタイズ試作プロジェクトの基本的な使用方法を説明します。

## プロジェクト構成

パレタイズ試作プロジェクトは、以下の複数のサブエージェントと管理コンポーネントで構成されています：

```
palletizing_prototype/
├── orchestrator/          # 全体統括
├── box_research/          # 箱仕様調査
├── algorithm_research/    # アルゴリズム方式調査
├── test_programmer/       # テストデータ作成
├── algorithm_programmer/  # パレタイズアルゴリズム実装
├── visualizer/            # 3D/2D可視化ツール
├── tester/                # テスト実行・シミュレーション
├── supervisor/            # 制約検証
└── constraints/           # 荷姿制約仕様
```

## エージェント構成と役割

### Orchestrator
- 他サブエージェントを統括する管理者
- ユーザーからの要望に応じて計画を立案
- プロジェクト全体の進行と整合性を管理

### Box Research
- 箱仕様（寸法、嵌合深さ、リブ厚み）の調査
- 箱データベースの作成・管理

### Algorithm Research
- 嵌合・リブ構造に対応したパレタイズ手法の調査
- アルゴリズム方式の提案

### Test Programmer
- テスト用の箱リスト作成
- 単載・混載等のテストパターン設計

### Algorithm Programmer
- パレタイズアルゴリズムの実装
- フィードバックをもとにプログラムの改良

### Visualizer
- アルゴリズム出力結果（配置座標、回転、積み順）の可視化
- 3D/2D描画ツールの開発・提供

### Tester
- テスト箱リストでアルゴリズムを実行
- 荷山形成シミュレーション実施
- エラーログの記録と報告

### Supervisor
- `constraints/constraints.md` に基づき制約検証
- 出力された荷姿が制約を満たしているか監視
- 制約違反の具体的な問題点を報告

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

## データフォーマット

### 箱データベース (`box_db`)

各箱の情報は以下の形式で管理されます：

```json
{
  "id": "box_001",
  "width": 600.0,
  "length": 400.0,
  "height": 300.0,
  "fitting_depth": 50.0,
  "rib_thickness": 5.0
}
```

### パレット仕様 (`pallet_spec`)

```json
{
  "width": 1200.0,
  "length": 1000.0,
  "max_height": 1500.0
}
```

### パレタイズ結果 (`palletize_result`)

```json
{
  "order": 1,
  "box_id": "box_001",
  "position": [100, 200, 50],
  "rotation": 0
}
```

---

**次のステップ**: [アルゴリズム説明](/palletizing_prototype/wiki/algorithm-explanation.html)を参照して技術詳細を確認してください。
