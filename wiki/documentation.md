---
layout: page
title: ドキュメント
---

# ドキュメント

本ページでは、プロジェクト全体のドキュメンテーション情報を提供します。

## プロジェクト構成

### ディレクトリ構造

```
palletizing_prototype/
├── constraints/               # 荷姿制約仕様書
├── box_research/              # 箱仕様調査レポート、箱DB
├── algorithm_research/        # アルゴリズム調査・方式提案書
├── test_programmer/           # テスト用箱リスト作成スクリプト
├── algorithm_programmer/      # パレタイズアルゴリズム実装
├── visualizer/                # 3D/2D可視化ツール
├── tester/                    # テスト実行スクリプト、シミュレーション結果
├── supervisor/                # 制約バリデーション
└── GEMINI.md                  # プロジェクト全体ルール
```

## 各サブエージェントの説明

### Box Research (`box_research/`)

**主な成果物**:
- `box_db.json`: 箱仕様データベース
- `investigation_report.md`: 調査レポート

**責務**:
- パレタイズ対象となる箱の寸法・嵌合深さ・リブ仕様を調査
- 箱情報をデータベース化して管理

### Algorithm Research (`algorithm_research/`)

**主な成果物**:
- `proposal.md`: アルゴリズム方式提案書

**責務**:
- 嵌合・リブ構造を考慮したパレタイズ手法を調査
- 本プロジェクトに適した方式を提案

### Test Programmer (`test_programmer/`)

**主な成果物**:
- テスト用箱リスト（JSON/CSV 形式）
- テストデータ生成スクリプト

**責務**:
- 箱データベースをもとにテスト・評価用の箱リストを作成
- 単載・混載等の投入パターンを設計

### Algorithm Programmer (`algorithm_programmer/`)

**主な成果物**:
- `palletizer.py`: メインのパレタイズアルゴリズム実装
- `constraints_engine.py`: 制約処理エンジン

**責務**:
- アルゴリズム研究成果に基づきパレタイズエンジンを実装
- フィードバックをもとに改良

### Visualizer (`visualizer/`)

**主な成果物**:
- `visualize.py`: 可視化スクリプト
- `viewer.html`: 3D/2D ビューワー（オプション）

**責務**:
- パレタイズ結果（配置座標、回転、積み順）を可視化
- 荷姿を3D/2Dで直感的に確認

### Tester (`tester/`)

**主な成果物**:
- `run_tests.py`: テスト実行スクリプト
- `test_results/`: テスト結果データ、ログファイル

**責務**:
- テスト箱リストでアルゴリズムを実行
- 荷山形成シミュレーション
- エラー発生時はログを記録

### Supervisor (`supervisor/`)

**主な成果物**:
- `validate.py`: 制約バリデーションスクリプト
- `validation_report.md`: 検証レポート

**責務**:
- `constraints/constraints.md` に基づき制約検証
- 荷姿が制約を満たしているか監視
- 制約違反を具体的に報告

## データフォーマット仕様

### 箱データベース (`box_db.json`)

```json
[
  {
    "id": "box_001",
    "width": 600.0,
    "length": 400.0,
    "height": 300.0,
    "fitting_depth": 50.0,
    "rib_thickness": 5.0
  }
]
```

**フィールド説明**:
- `id`: 箱の識別子（ユニーク）
- `width`: 外寸幅 [mm]
- `length`: 外寸奥行き [mm]
- `height`: 外寸高さ [mm]
- `fitting_depth`: 勘合深さ [mm]
- `rib_thickness`: リブ厚み [mm]

### パレット仕様

```json
{
  "width": 1200.0,
  "length": 1000.0,
  "max_height": 1500.0
}
```

### パレタイズ結果

```json
[
  {
    "order": 1,
    "box_id": "box_001",
    "position": [100, 200, 50],
    "rotation": 0
  }
]
```

**フィールド説明**:
- `order`: 積み込み順番（1, 2, 3, ...）
- `box_id`: 配置対象の箱ID
- `position`: 配置座標 (x, y, z) [mm]
- `rotation`: 箱の回転向き [度]

## 制約仕様ファイル

### constraints/constraints.md

荷姿制約は以下の項目を管理します：

- **嵌合ルール**: 上下に積み重ねられる箱の組み合わせ
- **リブ干渉制約**: リブが干渉しない最小距離
- **段数制限**: 最大積み段数
- **重量分散**: 重い箱の配置ルール（空箱のため割愛の場合あり）

---

## リソース

### 主要ドキュメント

- **GEMINI.md**: プロジェクト全体の構成とルール（リポジトリルート）

### GitHub リポジトリ

- [TakahiroNakadaTMC/palletizing_prototype](https://github.com/TakahiroNakadaTMC/palletizing_prototype)

---

**関連ページ**:
- [セットアップ&インストール](/palletizing_prototype/wiki/setup-installation.html)
- [使用ガイド](/palletizing_prototype/wiki/user-guide.html)
- [アルゴリズム説明](/palletizing_prototype/wiki/algorithm-explanation.html)
