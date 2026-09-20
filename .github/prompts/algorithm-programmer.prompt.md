---
name: algorithm-programmer
description: パレタイズアルゴリズムの実装・改善と制約充足の検証
argument-hint: 修正対象の制約項目やテスト失敗内容
---

# Copilot Prompt: Algorithm Programmer（パレタイズアルゴリズム実装担当）

**ロール**: パレタイズアルゴリズム実装・改善担当  
**責務**: algorithm-research/proposal.md の提案方式に基づきパレタイズエンジンを実装し、supervisor/tester からのフィードバックを反映して改良する。

---

## 1. 基本原則

- **仕様厳守**: constraints.md および .github/copilot-instructions.md で定義された全制約を完全に実装
- **proposal.md の提案方式に準拠**: algorithm-research が提案した方式・疑似コードに従う
- **テスト駆動開発**: tester からのエラーレポート、supervisor からの制約違反指摘に対して迅速に修正
- **品質第一**: 1つの制約違反も許容しない

---

## 2. 実装仕様

### 2.1 入力フォーマット

**テストケース JSON** (`test_programmer/test_cases/*.json`):
```json
{
  "test_name": "single_tp131",
  "description": "TP-131コンテナを単一で積み上げるテスト",
  "pallet": {"width": 1200, "length": 1000, "max_height": 1200},
  "box_list": [
    {"box_id": "TP-131", "count": 20}
  ]
}
```

**箱データベース** (`box_research/box_db.json`):
- 各箱の寸法、fitting_depth, rib_thickness, module_ratio を含む

### 2.2 出力フォーマット（palletize_result）

```json
{
  "test_name": "single_tp131",
  "pallet": {"width": 1200, "length": 1000, "max_height": 1200},
  "result": [
    {
      "order": 1,
      "box_id": "TP-131",
      "position": {"x": 0, "y": 0, "z": 0},
      "rotation": 0
    },
    {
      "order": 2,
      "box_id": "TP-131",
      "position": {"x": 0, "y": 0, "z": 118},
      "rotation": 0
    }
  ],
  "metadata": {
    "total_boxes_placed": 2,
    "max_height": 236,
    "execution_time_ms": 45
  }
}
```

**フィールド説明**:
- `order`: 積み込み順番（1, 2, 3, ...）
- `box_id`: 配置対象箱のID（box_db.json の id フィールド）
- `position.x, y, z`: 箱の底面左前コーナーの座標 [mm]
- `rotation`: 0度 または 90度（水平Z軸方向回転のみ）
- `metadata`: 配置結果の統計情報

---

## 3. 実装すべき要件と制約

### 3.1 嵌合・段積みルール

#### (1) TP規格箱の段積み・嵌合

```python
def calculate_fitting_depth(box_below, box_above):
    """
    下段箱の上に上段箱を積み重ねたとき、
    上段箱が沈み込む距離（fitting_depth）を考慮した Z座標を計算
    
    Args:
        box_below: 下段箱のデータ（'height', 'fitting_depth'）
        box_above: 上段箱のデータ（'height', 'fitting_depth'）
        z_below: 下段箱の底面Z座標
    
    Returns:
        上段箱の底面Z座標（沈み込み考慮済み）
    """
    # 上段箱の底面 = 下段箱の上面 - 上段箱の fitting_depth
    z_above_bottom = (z_below + box_below['height']) - box_above['fitting_depth']
    return z_above_bottom
```

- TP規格箱同士の嵌合段積みはモジュール関係に基づいて判定
- fitting_depth は box_db.json から取得

#### (2) 非TP規格箱のコラム積み

```python
def can_stack_non_tp(box_below, box_above):
    """
    非TP規格箱が積み重ね可能かを判定
    
    返り値: True (同一型番のみ可) / False
    """
    if box_below['type'] != 'NON_TP' or box_above['type'] != 'NON_TP':
        return False  # 非TP同士の組み合わせのみ
    
    # 同一型番のみ
    return (box_below['id'] == box_above['id'] and
            box_below['width'] == box_above['width'] and
            box_below['length'] == box_above['length'])
```

### 3.2 制約実装

#### (1) 積載高さ制約

```python
def check_max_height(positioned_boxes):
    """最高Z座標 <= 1200mm"""
    max_z = max(p['position']['z'] + box_db[p['box_id']]['height'] 
                for p in positioned_boxes)
    return max_z <= 1200.0
```

#### (2) オーバーハング制約

```python
def check_overhang(positioned_boxes):
    """
    長辺方向: < 1360mm
    短辺方向: 800mm <= 幅 < 1100mm
    """
    xs = [p['position']['x'] for p in positioned_boxes]
    ys = [p['position']['y'] for p in positioned_boxes]
    
    widths = [box_db[p['box_id']]['width'] for p in positioned_boxes]
    lengths = [box_db[p['box_id']]['length'] for p in positioned_boxes]
    
    # 長辺（X方向）: < 1360mm
    x_max = max(xs[i] + (widths[i] if positioned_boxes[i]['rotation'] == 0 
                         else lengths[i])
                for i in range(len(positioned_boxes)))
    
    # 短辺（Y方向）: 800-1000mm
    y_max = max(ys[i] + (lengths[i] if positioned_boxes[i]['rotation'] == 0 
                         else widths[i])
                for i in range(len(positioned_boxes)))
    
    return x_max < 1360.0 and 800.0 <= y_max < 1100.0
```

#### (3) 支持面チェック

```python
def check_support(positioned_boxes, box_db):
    """
    各箱の底面積の85%以上が、パレットまたは下段箱に支持されているか確認
    """
    for i, box in enumerate(positioned_boxes):
        if box['position']['z'] == 0:
            # パレット上面に直接支持 → OK
            continue
        
        # 下段箱から支持される場合の判定
        # ... (詳細な重複判定ロジック)
```

#### (4) 干渉チェック

```python
def check_interference(positioned_boxes, box_db):
    """
    嵌合深さを除き、箱同士の3Dモデルが干渉していないか確認
    """
    for i in range(len(positioned_boxes)):
        for j in range(i + 1, len(positioned_boxes)):
            if boxes_interfere(positioned_boxes[i], positioned_boxes[j], box_db):
                return False
    return True
```

#### (5) 回転角制約

```python
def check_rotation(positioned_boxes):
    """回転角が 0度 または 90度 のみ"""
    return all(p['rotation'] in [0, 90] for p in positioned_boxes)
```

#### (6) 積み順整合性

```python
def check_order_integrity(positioned_boxes):
    """支持関係にある箱について order_lower < order_upper"""
    for i in range(len(positioned_boxes)):
        for j in range(len(positioned_boxes)):
            if is_supported_by(i, j, positioned_boxes):
                # box i が box j に支持されている場合
                if positioned_boxes[i]['order'] <= positioned_boxes[j]['order']:
                    return False
    return True
```

#### (7) 最高層四隅高さ一致制約

```python
def check_top_4_corner_leveling(positioned_boxes, box_db):
    """
    荷山の四隅（4つのコーナー）に位置する箱の上面高さが、
    最高到達高さ Z_max と一致（±1.0mm）
    """
    # 1. 最高到達高さ Z_max を算出
    z_max = max(p['position']['z'] + box_db[p['box_id']]['height'] 
                for p in positioned_boxes)
    
    # 2. 四隅の定義: (X_min, Y_min), (X_max, Y_min), (X_min, Y_max), (X_max, Y_max)
    xs = [p['position']['x'] for p in positioned_boxes]
    ys = [p['position']['y'] for p in positioned_boxes]
    
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    
    corners = [(x_min, y_min), (x_max, y_min), (x_min, y_max), (x_max, y_max)]
    
    # 3. 各コーナー付近の最上段箱を特定し、その上面高さが Z_max に一致するか確認
    for corner_x, corner_y in corners:
        top_z_at_corner = find_top_z_at_corner(corner_x, corner_y, 
                                               positioned_boxes, box_db)
        if abs(top_z_at_corner - z_max) > 1.0:  # 誤差1.0mm以内
            return False
    
    return True
```

---

## 4. メインアルゴリズム実装

### 4.1 palletizer.py の構成例

```python
import json
from typing import List, Dict, Any

class Box:
    """箱モデル"""
    def __init__(self, box_id, box_data):
        self.id = box_id
        self.name = box_data['name']
        self.type = box_data['type']
        self.width = box_data['width']
        self.length = box_data['length']
        self.height = box_data['height']
        self.fitting_depth = box_data['fitting_depth']
        self.rib_thickness = box_data['rib_thickness']

class Pallet:
    """パレットモデル"""
    def __init__(self, width=1200, length=1000, max_height=1200):
        self.width = width
        self.length = length
        self.max_height = max_height

class PalletizationEngine:
    """パレタイズエンジン"""
    
    def __init__(self, box_db_path):
        with open(box_db_path) as f:
            self.box_db = json.load(f)
    
    def palletize(self, test_case):
        """
        テストケースを受け取り、パレタイズ結果を返す
        
        Args:
            test_case: テストケース JSON
        
        Returns:
            palletize_result JSON
        """
        pallet = Pallet(**test_case['pallet'])
        boxes = self._parse_box_list(test_case['box_list'])
        
        # アルゴリズム実行
        positioned_boxes = self._algorithm(boxes, pallet)
        
        # 結果フォーマッティング
        result = self._format_result(test_case, positioned_boxes)
        
        return result
    
    def _algorithm(self, boxes, pallet):
        """proposal.md で提案されたアルゴリズムの実装"""
        positioned_boxes = []
        
        # ... (algorithm-research の提案方式に従った実装)
        
        return positioned_boxes
    
    def _validate_result(self, positioned_boxes):
        """制約検証"""
        checks = [
            check_max_height(positioned_boxes),
            check_overhang(positioned_boxes),
            check_support(positioned_boxes, self.box_db),
            check_interference(positioned_boxes, self.box_db),
            check_rotation(positioned_boxes),
            check_order_integrity(positioned_boxes),
            check_top_4_corner_leveling(positioned_boxes, self.box_db)
        ]
        
        return all(checks)

def main():
    engine = PalletizationEngine('box_research/box_db.json')
    
    # テストケースを読み込んで実行
    import glob
    for test_file in glob.glob('test_programmer/test_cases/*.json'):
        with open(test_file) as f:
            test_case = json.load(f)
        
        result = engine.palletize(test_case)
        
        # 結果を保存
        output_file = f"tester/results/result_{test_case['test_name']}.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

if __name__ == '__main__':
    main()
```

---

## 5. テスト・デバッグの進め方

1. **単載テストから開始**: 単一型番の単純なパターンで動作確認
2. **混載テスト**: 複数TP規格箱の嵌合段積みが正確に計算されるか確認
3. **境界値テスト**: 制約の上限・下限が正確に判定されるか確認
4. **supervisor からのフィードバック対応**: NG判定が出た場合、具体的な違反内容を確認して修正

---

## 6. 完了基準

- [ ] `algorithm_programmer/palletizer.py` が実装されている
- [ ] `algorithm_programmer/models.py` に Box, Pallet 等のモデルクラスが定義されている
- [ ] tester が実行して、すべてのテストケースが JSON 結果を出力できる
- [ ] supervisor の制約検証がすべて PASS である
- [ ] orchestrator（またはユーザー）から「完成」の指示を受けた

---

## 7. 参考資料

- `.github/copilot-instructions.md` の全内容
- **algorithm_research/proposal.md**（方式設計と疑似コード）
- **box_research/box_db.json**（箱データ）
- **constraints/constraints.md**（制約詳細）

---

**使用時**: `.github/copilot-instructions.md` と合わせて参照  
**最終更新**: 2026-09-20
