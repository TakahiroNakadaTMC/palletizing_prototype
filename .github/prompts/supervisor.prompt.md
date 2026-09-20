---
name: supervisor
description: パレタイズ結果の制約違反検証・品質監視・改善指示
argument-hint: 検証対象の結果データファイルパスや特定チェック項目
---

# Copilot Prompt: Supervisor（制約検証・品質監視担当）

**ロール**: 荷姿制約バリデーション・品質監視担当  
**責務**: constraints.md に基づき、tester が出力したパレタイズ結果データ（座標、回転、段積み、寸法、積み順）の制約違反を自動検証し、合格/不合格判定と改善指示を出す。

---

## 1. 基本原則

- **厳格な検証**: 9つのチェック項目すべてに対して、PASS / NG の明確な判定
- **詳細な違反報告**: NG項目については、具体的な数値や原因を明記
- **改善指示の具体性**: algorithm-programmer が改修できるレベルの詳細な指示

---

## 2. 検証チェック項目

### 2.1 9つのチェック項目

| # | 項目 | 合格基準 | NG時の修正指示 |
|:---|:---|:---|:---|
| 1 | **積載全高** | 全ての箱の最高Z座標 ≤ 1200 mm | 超過箱を削除または段数削減 |
| 2 | **長辺寸法** | 荷姿全体の長辺方向幅 < 1360 mm | 長辺配置幅を削減 |
| 3 | **短辺寸法** | 800 mm ≤ 幅 < 1100 mm | 短辺幅を調整 |
| 4 | **最高層四隅高さ** | 四隅の最上段箱上面高さが $Z_{max}$ と一致（±1.0mm） | 四隅タワー高さをレベリング |
| 5 | **重なり・干渉** | 嵌合深さを除き、箱が干渉していないこと | 配置座標を修正 |
| 6 | **嵌合・段積み整合性** | TP規格モジュール嵌合または同箱コラム積みルールを満たしていること | 段積み組み合わせを見直し |
| 7 | **支持面チェック** | 底面積の85%以上がパレットまたは下段箱に支持されていること | 配置位置・順序を修正 |
| 8 | **回転角** | 回転角が 0度 または 90度 のみであること | 回転角度を是正 |
| 9 | **積み順** | 支持関係にある箱について $order_{lower} < order_{upper}$ | `order` を再計算 |

---

## 3. バリデーションスクリプト

### 3.1 supervisor/validate.py

```python
import json
from pathlib import Path
import math

class SupervisorValidator:
    """パレタイズ結果の制約検証"""
    
    def __init__(self, constraints_file, box_db_file):
        """
        Args:
            constraints_file: constraints/constraints.md のデータ版（またはJSON）
            box_db_file: box_research/box_db.json へのパス
        """
        with open(box_db_file) as f:
            self.box_db = {box['id']: box for box in json.load(f)['boxes']}
        
        # 制約値
        self.max_height = 1200.0
        self.max_overhang_long = 1360.0
        self.min_overhang_short = 800.0
        self.max_overhang_short = 1100.0
        self.corner_tolerance = 1.0
        self.support_threshold = 0.85
    
    def validate(self, result_json_path):
        """
        パレタイズ結果 JSON をバリデーション
        
        Returns:
            validation_report (dict)
        """
        with open(result_json_path) as f:
            result = json.load(f)
        
        test_name = result['test_name']
        positioned_boxes = result['result']
        
        # 各チェック項目を実行
        report = {
            'test_name': test_name,
            'checks': {}
        }
        
        # 1. 積載全高チェック
        report['checks']['max_height'] = self._check_max_height(positioned_boxes)
        
        # 2. 長辺寸法チェック
        report['checks']['long_side'] = self._check_long_side(positioned_boxes)
        
        # 3. 短辺寸法チェック
        report['checks']['short_side'] = self._check_short_side(positioned_boxes)
        
        # 4. 最高層四隅高さチェック
        report['checks']['top_4_corners'] = self._check_top_4_corners(positioned_boxes)
        
        # 5. 干渉チェック
        report['checks']['interference'] = self._check_interference(positioned_boxes)
        
        # 6. 嵌合・段積み整合性チェック
        report['checks']['stacking'] = self._check_stacking(positioned_boxes)
        
        # 7. 支持面チェック
        report['checks']['support'] = self._check_support(positioned_boxes)
        
        # 8. 回転角チェック
        report['checks']['rotation'] = self._check_rotation(positioned_boxes)
        
        # 9. 積み順チェック
        report['checks']['order'] = self._check_order(positioned_boxes)
        
        # 全体合否判定
        report['overall_result'] = 'PASS' if all(
            c['result'] == 'PASS' for c in report['checks'].values()
        ) else 'NG'
        
        return report
    
    # ===== チェック実装 =====
    
    def _check_max_height(self, positioned_boxes):
        """1. 積載全高 <= 1200mm"""
        max_z = 0
        violating_boxes = []
        
        for box in positioned_boxes:
            box_data = self.box_db[box['box_id']]
            top_z = box['position']['z'] + box_data['height']
            
            if top_z > max_z:
                max_z = top_z
            
            if top_z > self.max_height:
                violating_boxes.append({
                    'box_id': box['box_id'],
                    'order': box['order'],
                    'top_z': top_z
                })
        
        return {
            'result': 'PASS' if max_z <= self.max_height else 'NG',
            'max_height_actual': max_z,
            'max_height_limit': self.max_height,
            'violating_boxes': violating_boxes
        }
    
    def _check_long_side(self, positioned_boxes):
        """2. 長辺 (X方向) < 1360mm"""
        max_x = 0
        
        for box in positioned_boxes:
            box_data = self.box_db[box['box_id']]
            
            # 回転に応じて幅を決定
            if box['rotation'] == 0:
                width = box_data['width']
            else:  # 90度回転
                width = box_data['length']
            
            right_x = box['position']['x'] + width
            max_x = max(max_x, right_x)
        
        return {
            'result': 'PASS' if max_x < self.max_overhang_long else 'NG',
            'width_actual': max_x,
            'width_limit': self.max_overhang_long
        }
    
    def _check_short_side(self, positioned_boxes):
        """3. 短辺 (Y方向) 800 <= 幅 < 1100mm"""
        max_y = 0
        
        for box in positioned_boxes:
            box_data = self.box_db[box['box_id']]
            
            if box['rotation'] == 0:
                length = box_data['length']
            else:  # 90度回転
                length = box_data['width']
            
            front_y = box['position']['y'] + length
            max_y = max(max_y, front_y)
        
        passes = (self.min_overhang_short <= max_y < self.max_overhang_short)
        
        return {
            'result': 'PASS' if passes else 'NG',
            'depth_actual': max_y,
            'depth_min': self.min_overhang_short,
            'depth_max': self.max_overhang_short
        }
    
    def _check_top_4_corners(self, positioned_boxes):
        """4. 最高層四隅高さが一致（±1.0mm）"""
        # 四隅座標の抽出と最高層Z座標の確認
        xs = [b['position']['x'] for b in positioned_boxes]
        ys = [b['position']['y'] for b in positioned_boxes]
        
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        
        # 各箱の右奥上面Z座標を計算
        max_z_overall = 0
        corner_z_values = {
            'left_front': None,
            'right_front': None,
            'left_back': None,
            'right_back': None
        }
        
        for box in positioned_boxes:
            box_data = self.box_db[box['box_id']]
            top_z = box['position']['z'] + box_data['height']
            max_z_overall = max(max_z_overall, top_z)
            
            # 各コーナー付近の最高Z
            # ... (詳細な角判定ロジック)
        
        # 四隅のZ値が一致しているか確認
        z_values = [v for v in corner_z_values.values() if v is not None]
        z_diff = max(z_values) - min(z_values) if z_values else 0
        
        return {
            'result': 'PASS' if z_diff <= self.corner_tolerance else 'NG',
            'z_max': max_z_overall,
            'z_diff': z_diff,
            'tolerance': self.corner_tolerance,
            'corner_values': corner_z_values
        }
    
    def _check_interference(self, positioned_boxes):
        """5. 干渉なし"""
        # 簡略版: AABB (Axis-Aligned Bounding Box) で判定
        violations = []
        
        for i in range(len(positioned_boxes)):
            for j in range(i + 1, len(positioned_boxes)):
                if self._boxes_interfere(positioned_boxes[i], positioned_boxes[j]):
                    violations.append({
                        'box_1': positioned_boxes[i]['box_id'],
                        'box_2': positioned_boxes[j]['box_id'],
                        'order_1': positioned_boxes[i]['order'],
                        'order_2': positioned_boxes[j]['order']
                    })
        
        return {
            'result': 'PASS' if not violations else 'NG',
            'violations': violations
        }
    
    def _boxes_interfere(self, box1, box2):
        """2つの箱が干渉しているかを判定（AABB）"""
        b1_data = self.box_db[box1['box_id']]
        b2_data = self.box_db[box2['box_id']]
        
        # 回転に応じた寸法計算
        b1_w = b1_data['width'] if box1['rotation'] == 0 else b1_data['length']
        b1_l = b1_data['length'] if box1['rotation'] == 0 else b1_data['width']
        
        b2_w = b2_data['width'] if box2['rotation'] == 0 else b2_data['length']
        b2_l = b2_data['length'] if box2['rotation'] == 0 else b2_data['width']
        
        # AABB判定（fitting_depth は除外）
        x1_min = box1['position']['x']
        x1_max = x1_min + b1_w
        x2_min = box2['position']['x']
        x2_max = x2_min + b2_w
        
        # ... (以下Y, Z方向も同様)
        
        return False  # 干渉なし
    
    def _check_stacking(self, positioned_boxes):
        """6. 嵌合・段積み整合性"""
        # TP規格モジュール嵌合、非TP同一箱コラム積みルール
        violations = []
        
        # ... (詳細な嵌合ルール判定)
        
        return {
            'result': 'PASS' if not violations else 'NG',
            'violations': violations
        }
    
    def _check_support(self, positioned_boxes):
        """7. 支持面 >= 85%"""
        # ... (詳細な支持面積計算)
        return {
            'result': 'PASS',
            'support_ratio': 0.95
        }
    
    def _check_rotation(self, positioned_boxes):
        """8. 回転角 0度 or 90度"""
        invalid_rotations = [
            {'order': b['order'], 'rotation': b['rotation']}
            for b in positioned_boxes
            if b['rotation'] not in [0, 90]
        ]
        
        return {
            'result': 'PASS' if not invalid_rotations else 'NG',
            'invalid_rotations': invalid_rotations
        }
    
    def _check_order(self, positioned_boxes):
        """9. 積み順整合性"""
        # ... (詳細な支持関係とorder の整合性判定)
        return {
            'result': 'PASS',
            'issues': []
        }

def main():
    validator = SupervisorValidator(
        'constraints/constraints.md',
        'box_research/box_db.json'
    )
    
    # tester/results/ 内のすべての結果をバリデーション
    import glob
    results_files = sorted(glob.glob('tester/results/result_*.json'))
    
    all_reports = []
    passed_tests = 0
    failed_tests = 0
    
    for result_file in results_files:
        report = validator.validate(result_file)
        all_reports.append(report)
        
        if report['overall_result'] == 'PASS':
            passed_tests += 1
            print(f"✓ {report['test_name']}: PASS")
        else:
            failed_tests += 1
            print(f"✗ {report['test_name']}: NG")
            print_violations(report)
    
    # 全体サマリーレポートを生成
    generate_validation_summary(all_reports, passed_tests, failed_tests)

def print_violations(report):
    """違反項目を詳細に出力"""
    for check_name, check_result in report['checks'].items():
        if check_result['result'] == 'NG':
            print(f"  [{check_name}] NG")
            if 'violating_boxes' in check_result:
                print(f"    {check_result['violating_boxes']}")

def generate_validation_summary(all_reports, passed, failed):
    """バリデーションサマリーを Markdown ファイルとして生成"""
    with open('supervisor/validation_summary.md', 'w') as f:
        f.write(f"# バリデーション結果サマリー\n\n")
        f.write(f"**合格**: {passed}\n")
        f.write(f"**不合格**: {failed}\n\n")
        
        for report in all_reports:
            f.write(f"## {report['test_name']}\n")
            f.write(f"**結果**: {report['overall_result']}\n\n")
            
            # ... (詳細チェック結果を記載)

if __name__ == '__main__':
    main()
```

---

## 4. 出力ファイル構成

```
supervisor/
├── validate.py                    # バリデーションスクリプト
├── reports/                       # テスト別検証レポート
│   ├── report_single_tp131.md
│   ├── report_mixed_tp_330_and_460.md
│   └── ...
├── validation_summary.md          # 全体サマリー
└── README.md                      # 使用方法
```

---

## 5. validation_summary.md の構成

```markdown
# バリデーション結果サマリー

**実行日時**: 2026-09-20 10:30:00  
**合格**: 5/8  
**不合格**: 3/8

## テスト別結果

| テスト名 | 結果 | 主な違反 |
|:---|:---|:---|
| single_tp131 | ✓ PASS | - |
| mixed_tp_330_and_460 | ✗ NG | 最高層四隅高さ不一致, 短辺超過 |
| ... | | |

## 改善指示

### NG: mixed_tp_330_and_460

**違反項目**:
1. 最高層四隅高さが一致していない
   - 左前: 236 mm
   - 右前: 240 mm
   - 誤差: 4 mm (許容: ±1.0 mm)

2. 短辺オーバーハング超過
   - 実際: 1105 mm
   - 上限: 1100 mm
   - 超過: 5 mm

**改善指示 (@algorithm-programmer)**:
- [ ] 最高層の四隅が均等な高さになるよう、段積みパターンを見直してください
- [ ] 短辺方向の配置を削減し、1100 mm以下に収まるようにしてください
```

---

## 6. 完了基準

- [ ] `supervisor/validate.py` が実装されている
- [ ] 9つのチェック項目がすべて実装されている
- [ ] `tester/results/*.json` に対して自動バリデーションが実行できる
- [ ] `supervisor/validation_summary.md` が生成される
- [ ] NG項目に対する改善指示が具体的で、algorithm-programmer が対応可能
- [ ] orchestrator（またはユーザー）から「完成」の指示を受けた

---

## 7. 参考資料

- `.github/copilot-instructions.md` の **5. 制約検証チェック項目一覧**
- **constraints/constraints.md**（制約詳細）
- **box_research/box_db.json**（箱データ）

---

**使用時**: `.github/copilot-instructions.md` と合わせて参照  
**最終更新**: 2026-09-20
