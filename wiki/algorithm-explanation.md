---
layout: page
title: アルゴリズム説明
permalink: /wiki/algorithm-explanation/
---

# アルゴリズム説明

本ページでは、**HM-Palletizer** パレタイズアルゴリズムの技術的な詳細を説明します。

## アルゴリズムの概要

HM-Palletizer は、以下の制約条件下で箱をパレットに効率的に配置することを目標とした統合パレタイズシステムです：

- **嵌合制約**: 上下の箱が勘合する深さ（fitting_depth）を考慮
- **TP規格モジュール嵌合**: TP規格コンテナの段積みボーナスと許容パターン
- **境界制限**: 長辺 < 1360mm、短辺 800mm〜1100mm 以内に収納
- **四隅高さ揃え**: 最上層の四隅が同じ高さに到達（荷崩れ防止）
- **リブ干渉回避**: 箱の外周リブが干渉しないように配置
- **支持面判定**: 下層との接地面積85%以上を要求（空中浮き防止）

---

## 主要コンポーネント

### 1. 箱データモデル (BoxSpec)

各箱は以下の属性を持ちます：

```python
BoxSpec:
  - id: 箱型番（例: "TP-462"）
  - type: "TP" または "NON_TP"
  - width: 外寸幅 [mm]
  - length: 外寸奥行 [mm]
  - height: 外寸高さ [mm]
  - fitting_depth: 嵌合沈み込み深さ [mm]
  - rib_thickness: 側面リブ厚み [mm]
  - module_ratio: TP規格モジュール比（"1x1", "1.5x1", "2x1" など）
```

### 2. パレット仕様 (PalletSpec)

```python
PalletSpec:
  - width: 1200mm（X軸 長辺）
  - length: 1000mm（Y軸 短辺）
  - max_height: 1200mm（Z軸 最大積載高）
  - max_x_span: 1360mm（長辺荷姿許容上限）
  - min_y_span: 800mm（短辺荷姿最小幅）
  - max_y_span: 1100mm（短辺荷姿最大幅）
```

### 3. 配置結果 (PlacedBox)

各配置済みの箱は以下を記録：

```python
PlacedBox:
  - order: 積載順序（1, 2, 3, ...）
  - box_id: 箱型番
  - x, y, z: 配置座標 [mm]
  - width, length, height: 配置後の寸法
  - rotation: 0度 または 90度
  - layer_index: 段数インデックス（0, 1, 2, ...）
  - supported_by: 支持している下段の箱のorderリスト
```

---

## 嵌合・リブ構造の処理方法

### 嵌合深さ (Fitting Depth)

上下に積み重ねた箱は、勘合により一定深さまではまり込みます。

**Z座標計算の原理**:

```
Layer 0: z₀ = 0
Layer 1: z₁ = (h₀ - fitting_depth₀)
Layer 2: z₂ = (h₀ - fitting_depth₀) + (h₁ - fitting_depth₁)
...
max_layers = ⌊(max_height - h) / (h - fitting_depth)⌋ + 1
```

**具体例**:
- 箱高さ: 300mm、嵌合深さ: 50mm
- Layer 0: Z = 0mm（高さ 300mm）
- Layer 1: Z = 250mm（高さ 300mm、実質的な積み上がり = 250mm）
- Layer 2: Z = 500mm
- パレット高さ制限 1200mm の場合、最大 5 層まで積載可能

### 嵌合Z座標ソルバー

混載パレタイズにおいて、異なる高さの箱が上下に積み重なる場合：

```
Z_new = max(Z_top[j] - fitting_depth[j] for j in SupportingBoxes)
```

これにより、下層の箱の形状に合わせた最適な嵌合が自動計算されます。

### リブ干渉判定

隣接する箱の距離を検証：

```
if distance(Box₁, Box₂) < rib_thickness₁ + rib_thickness₂:
  → 干渉エラー（配置不可）
else:
  → 安全に隣接可能
```

---

## アルゴリズムフロー

### 全体処理フロー

```
1. 入力：箱リスト、パレット仕様
   
2. 単載判定：すべての箱が同一型番か？
   ├─ YES → palletize_single() へ
   └─ NO → palletize_mixed() へ

3. (単載の場合)
   - 2D配置パターン生成（0度、90度、スプリット分割）
   - 制約枠フィルタリング（長辺<1360mm、短辺800-1100mm）
   - 最高効率パターン選定
   - 層ごとに箱を配置、インターロッキング（奇数層で反転）

4. (混載の場合)
   - 箱をフットプリント・高さで分類
   - 層単位でのパッキング（拡張 Extreme Points 法）
   - 嵌合Z座標ソルバー適用
   - 支持面判定（85%以上接地を確認）
   - 四隅が揃わない中途半端な層は削除

5. 最高層四隅高さ揃え (Level Top 4-Corners)
   - パレット四隅周辺の箱の最高位置を検出
   - 高さ不一致時に箱の移動または削除を判定

6. 積み順決定 (Topological Sort)
   - Z座標昇順 → Y座標昇順 → X座標昇順 でソート
   - order = 1, 2, 3, ... を付番
   - supported_by = 支持下層の order リストを記録

7. サマリー計算
   - バウンディングボックス（x_span, y_span, max_z）
   - 体積効率率（%）
   - 制約違反の検査
   - 四隅高さ一致確認

8. 出力：PlacedBox[], summary, 未配置箱リスト
```

---

## 単載パレタイズ (palletize_single)

同一型番の箱のみを積み上げる効率的なパターンマッチング方式です。

### パターン生成戦略

#### パターン 1: グリッド 0度配置
```
n_x = ⌊max_x_span / width⌋
n_y = ⌊max_y_span / length⌋
各層に n_x × n_y 個の箱を配置
```

#### パターン 2: グリッド 90度配置
```
n_x = ⌊max_x_span / length⌋
n_y = ⌊max_y_span / width⌋
各層に n_x × n_y 個の箱を配置（回転）
```

#### パターン 3: スプリット分割（レンガ積み）
```
X方向分割：
  左側: n_x0 × n_y0 個（0度）
  右側: n_x90 × n_y2 個（90度）
→ 余剰スペースを活用

Y方向分割：
  上側: n_x0 × n_y0 個（0度）
  下側: n_x2 × n_y90 個（90度）
→ 異方向組み合わせで効率向上
```

### パターン選定基準

1. **制約フィルタリング**:
   - x_span < 1360mm ✓
   - 800mm ≤ y_span < 1100mm ✓

2. **ソート順序**:
   - 最大収納数（層あたりボックス数）を優先
   - 次に y_span の最小化（パレット利用効率）

3. **インターロッキング**（荷崩れ防止）:
   ```
   Layer 0: 通常配置
   Layer 1: 180度回転（反転）
   Layer 2: 通常配置
   ...
   ```

### 中央配置オフセット計算

```python
offset_x = (pallet.width - x_span) / 2.0
offset_y = (pallet.length - y_span) / 2.0
```

パレット中央にセンタリングされます。

---

## 混載パレタイズ (palletize_mixed)

異なる型番・高さの箱を組み合わせる高度なアルゴリズムです。

### 拡張 Extreme Points 法

各層でのパッキング位置候補を列挙：

```
Extreme Points EP = {配置済み箱の角からの候補位置}

候補位置ごとに：
1. 回転パターン（0度、90度）を試す
2. 既存箱との2D干渉判定
3. パレット境界チェック
4. 嵌合Z座標の計算
5. 支持面判定（85%以上接地を要求）
6. 多目的スコア計算
```

### 嵌合Z座標ソルバー

下層の複数の箱の上に新しい箱を置く場合：

```
接地候補 = {下層の箱で、2D投影が重なるもの}

Z_new = max(top_z[j] - fitting_depth[j] for j in 接地候補)
```

### 支持面判定

```
接地面積 = 新箱の底面 ∩ すべての支持箱の上面
必要な接地面積 = 新箱の底面積 × 0.85

if 接地面積 ≥ 必要接地面積:
  ✓ 配置可能
else:
  ✗ 空中浮き判定で不可
```

### 四隅高さ揃え処理 (level_top_four_corners)

1. **四隅定義**:
   ```
   Margin = 35mm（コーナー判定の範囲）
   Corner 1: (min_x, min_y)
   Corner 2: (max_x, min_y)
   Corner 3: (min_x, max_y)
   Corner 4: (max_x, max_y)
   ```

2. **四隅の最高高さ検出**:
   ```
   for each corner:
     h_corner = max(top_z of boxes touching this corner)
   ```

3. **高さ一致判定**:
   ```
   if max(h₁, h₂, h₃, h₄) - min(h₁, h₂, h₃, h₄) ≤ 1.0mm:
     ✓ 四隅が揃っている
   else:
     ✗ 不一致（高いコーナーに合わせるか、層全体を削除）
   ```

---

## 積み順決定 (Topological Sort)

トポロジカルソート + Z優先順での決定法：

```python
# 1. 昇順ソート
sorted_boxes = sorted(
    placed_boxes,
    key=lambda b: (round(b.z, 2), round(b.y, 2), round(b.x, 2))
)

# 2. order を順序に従い付番（1, 2, 3, ...）
for idx, pb in enumerate(sorted_boxes, start=1):
    pb.order = idx

# 3. 支持下層の検索
for each pb:
    for each already_placed_box:
        if 2D投影が重なり AND
           下層の top_z ≈ pb.z + pb.fitting_depth:
            → pb.supported_by に追加
```

**利点**:
- 下段の箱から上段へ、積み上げ順序に従った order 付番
- 支持関係を明確に記録
- ローディングシーケンスの逆順が自動的に得られる

---

## 制約検証とサマリー計算

### 制約チェック項目

```python
violations = []

# 1. 最大高さチェック
if max_z > pallet.max_height:
    violations.append("Max height exceeded")

# 2. 長辺スパンチェック
if x_span >= pallet.max_x_span:
    violations.append("Long side span exceeded")

# 3. 短辺スパン範囲チェック
if y_span < pallet.min_y_span OR y_span >= pallet.max_y_span:
    violations.append("Short side span out of range")

# 4. 四隅高さ一致チェック
if corners_height_variance > 1.0mm:
    violations.append("Top 4-corners height mismatch")
```

### 体積効率率計算

```
total_box_volume = Σ(width × length × height of all placed boxes)
pallet_volume = pallet.width × pallet.length × pallet.max_height

volume_efficiency_percent = (total_box_volume / pallet_volume) × 100
```

---

## パフォーマンス最適化

### 1. 計算量削減

| 要素 | 最適化手法 |
|------|----------|
| 2D干渉判定 | 軸並列分離定理（AABB） |
| Z座標計算 | 支持下層の最大値で O(1)計算 |
| 層ごとパッキング | Extreme Points 候補の限定 |
| パターン生成 | 制約による事前フィルタリング |

### 2. メモリ効率

- 占有率の高いパターンを優先探索 → 早期終了
- 不可能な配置は即座に枝刈り
- 層単位での処理により局所的なメモリ使用量を限定

### 3. 複雑度の例

| シナリオ | 時間計算量 | 空間計算量 |
|---------|-----------|----------|
| 単載（最適パターン）| O(pattern_count) | O(1) |
| 混載 N 個の箱 | O(N² × layers) | O(N) |

---

## 実装例

### CLI 実行

```bash
# テストケースの実行
python3 algorithm_programmer/cli.py \
  test_programmer/test_cases/mixed_tp_same_height.json

# 結果をJSONに出力
python3 algorithm_programmer/cli.py \
  test_programmer/test_cases/mixed_tp_same_height.json \
  -o tester/results/result_mixed_tp_same_height.json
```

### 出力フォーマット

```json
{
  "test_name": "mixed_tp_same_height",
  "pallet": {
    "width": 1200,
    "length": 1000,
    "max_height": 1200
  },
  "placed_boxes_count": 12,
  "boxes": [
    {
      "order": 1,
      "box_id": "TP-462",
      "position": {"x": 265.0, "y": 248.5, "z": 0.0},
      "dimensions": {"width": 670.0, "length": 503.0, "height": 300.0},
      "rotation": 0,
      "layer_index": 0,
      "supported_by": []
    },
    ...
  ],
  "summary": {
    "total_boxes": 12,
    "total_layers": 2,
    "bounding_box": {
      "x_span": 1340.0,
      "y_span": 1006.0,
      "max_z": 550.0
    },
    "volume_efficiency_percent": 48.25,
    "is_valid": true,
    "violations": []
  }
}
```

---

## 今後の改善方向

- **遺伝的アルゴリズム**: パターン組み合わせの多目的最適化
- **機械学習**: ヒューリスティック係数の自動調整
- **並列処理**: 複数の層を並行してパッキング
- **重心分析**: 荷重バランスの事前検証

---

**次のステップ**: [ドキュメント](/palletizing_prototype/wiki/documentation.html)を参照してプロジェクト全体の詳細情報を確認してください。
