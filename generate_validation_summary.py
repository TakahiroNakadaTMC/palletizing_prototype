#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supervisor: 制約バリデーション サマリー生成スクリプト

既存の tester/results/*.json から constraints.md に基づいた
制約検証を実施し、validation_summary.md を生成
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Windows環境での文字コード対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def validate_palletize_result(result_data, constraints):
    """パレタイズ結果を制約に照らして検証"""
    
    violations = []
    checks = {}
    
    # パレット仕様
    pallet_spec = result_data.get('pallet', {})
    max_height_limit = pallet_spec.get('max_height', 1200.0)
    max_x_span_limit = pallet_spec.get('max_x_span', 1360.0)
    min_y_span_limit = pallet_spec.get('min_y_span', 800.0)
    max_y_span_limit = pallet_spec.get('max_y_span', 1100.0)
    
    # 配置されたボックス
    boxes = result_data.get('boxes', [])
    
    # 1. 積載全高チェック
    if boxes:
        max_z = max(
            b.get('position', {}).get('z', 0) + b.get('dimensions', {}).get('height', 0)
            for b in boxes
        )
        if max_z <= max_height_limit:
            checks['max_height'] = 'PASS'
        else:
            checks['max_height'] = 'FAIL'
            violations.append(f"積載高さ超過: {max_z:.0f}mm > {max_height_limit:.0f}mm")
    else:
        checks['max_height'] = 'UNKNOWN'
    
    # 2. 長辺荷姿寸法チェック (X方向)
    if boxes:
        min_x = min(b.get('position', {}).get('x', 0) for b in boxes)
        max_x = max(
            b.get('position', {}).get('x', 0) + b.get('dimensions', {}).get('width', 0)
            for b in boxes
        )
        x_span = max_x - min_x
        if x_span < max_x_span_limit:
            checks['overhang_long'] = 'PASS'
        else:
            checks['overhang_long'] = 'FAIL'
            violations.append(f"長辺制限超過(X): {x_span:.0f}mm > {max_x_span_limit:.0f}mm")
    else:
        checks['overhang_long'] = 'UNKNOWN'
    
    # 3. 短辺荷姿寸法チェック (Y方向)
    if boxes:
        min_y = min(b.get('position', {}).get('y', 0) for b in boxes)
        max_y = max(
            b.get('position', {}).get('y', 0) + b.get('dimensions', {}).get('length', 0)
            for b in boxes
        )
        y_span = max_y - min_y
        if min_y_span_limit <= y_span <= max_y_span_limit:
            checks['short_side'] = 'PASS'
        else:
            checks['short_side'] = 'FAIL'
            violations.append(f"短辺制限外(Y): {y_span:.0f}mm (期待: {min_y_span_limit:.0f}-{max_y_span_limit:.0f}mm)")
    else:
        checks['short_side'] = 'UNKNOWN'
    
    # 4. 回転角チェック (0度 or 90度のみ)
    if boxes:
        invalid_rotations = [b for b in boxes if b.get('rotation', 0) not in [0, 90]]
        if not invalid_rotations:
            checks['rotation'] = 'PASS'
        else:
            checks['rotation'] = 'FAIL'
            violations.append(f"不正な回転角: {len(invalid_rotations)}個の箱が0度/90度以外")
    else:
        checks['rotation'] = 'UNKNOWN'
    
    # 5. 積み順チェック
    if boxes:
        orders = sorted([b.get('order', 0) for b in boxes])
        expected_orders = list(range(1, len(boxes) + 1))
        if orders == expected_orders:
            checks['order_consistency'] = 'PASS'
        else:
            checks['order_consistency'] = 'FAIL'
            violations.append(f"積み順が不連続: {len(boxes)}個のボックスで期待値と異なる")
    else:
        checks['order_consistency'] = 'UNKNOWN'
    
    return checks, violations

def generate_validation_summary():
    """制約バリデーション結果サマリーを生成"""
    project_root = Path(__file__).parent
    results_dir = project_root / 'tester' / 'results'
    
    if not results_dir.exists():
        print(f"❌ {results_dir} が見つかりません")
        return False
    
    # constraints.md 読み込み
    constraints_file = project_root / 'constraints' / 'constraints.md'
    with open(constraints_file, 'r', encoding='utf-8') as f:
        constraints = f.read()
    
    # 結果ファイルの読み込みと検証
    validation_results = []
    for result_file in sorted(results_dir.glob('result_*.json')):
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                result_data = json.load(f)
                checks, violations = validate_palletize_result(result_data, constraints)
                
                validation_results.append({
                    'test_name': result_data.get('test_name', '不明'),
                    'status': result_data.get('status', 'unknown'),
                    'checks': checks,
                    'violations': violations,
                    'result_data': result_data
                })
        except Exception as e:
            print(f"⚠️  {result_file.name} の検証エラー: {e}")
    
    print(f"✅ {len(validation_results)} 個のテスト結果を検証\n")
    
    # validation_summary.md の生成
    summary_content = f"""# 制約バリデーション結果レポート

**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**検証対象**: constraints/constraints.md の制約仕様  
**テストケース**: {len(validation_results)}個

---

## 検証結果一覧

| # | テスト名 | 総合 | 積載高さ | 長辺 | 短辺 | 回転角 | 積み順 | 違反数 |
|---|---------|------|---------|------|------|--------|--------|--------|
"""
    
    passed_tests = 0
    failed_tests = 0
    
    for idx, val_result in enumerate(validation_results, 1):
        test_name = val_result['test_name']
        checks = val_result['checks']
        violations = val_result['violations']
        
        # 総合判定
        overall = 'PASS' if not violations else 'FAIL'
        overall_symbol = '✅' if overall == 'PASS' else '❌'
        
        if overall == 'PASS':
            passed_tests += 1
        else:
            failed_tests += 1
        
        # 各チェック結果
        def check_symbol(status):
            return '✅' if status == 'PASS' else ('❌' if status == 'FAIL' else '⚠️')
        
        height = checks.get('max_height', 'UNKNOWN')
        overhang = checks.get('overhang_long', 'UNKNOWN')
        short = checks.get('short_side', 'UNKNOWN')
        rotation = checks.get('rotation', 'UNKNOWN')
        order = checks.get('order_consistency', 'UNKNOWN')
        
        summary_content += f"| {idx} | {test_name} | {overall_symbol} {overall} | {check_symbol(height)} | {check_symbol(overhang)} | {check_symbol(short)} | {check_symbol(rotation)} | {check_symbol(order)} | {len(violations)} |\n"
    
    summary_content += f"""
---

## 検証統計

| 項目 | 結果 |
|-----|------|
| **テスト合格** | {passed_tests}/{len(validation_results)} ({(passed_tests/len(validation_results)*100 if validation_results else 0):.1f}%) |
| **テスト不合格** | {failed_tests}/{len(validation_results)} ({(failed_tests/len(validation_results)*100 if validation_results else 0):.1f}%) |

---

## 違反内容の詳細

"""
    
    violation_count = 0
    for val_result in validation_results:
        violations = val_result['violations']
        if violations:
            violation_count += 1
            summary_content += f"""
### {val_result['test_name']} - 違反内容

"""
            for violation in violations:
                summary_content += f"- {violation}\n"
    
    if violation_count == 0:
        summary_content += """
✅ **制約違反なし** - 全テストが制約仕様を満たしています

"""
    
    summary_content += """
---

## 制約仕様の確認

### 検証項目

1. **積載全高**: Z_max <= 1200mm
2. **長辺荷姿寸法**: X_max (or Y_max) < 1360mm
3. **短辺荷姿寸法**: Min(X, Y) >= 800mm AND <= 1100mm
4. **回転角度**: 0度 or 90度のみ
5. **積み順**: 下段から上段への整合性

### 合格基準

- **PASS**: 全制約を満たす
- **FAIL**: 1つ以上の制約違反がある

---

## 推奨アクション

"""
    
    if failed_tests > 0:
        summary_content += f"""
### ⚠️ {failed_tests}個のテストが不合格

**確認・対応:**
1. 違反内容を上記で確認
2. Algorithm-programmer の修正ポイントを特定
3. 以下の修正が必要:

"""
        for val_result in validation_results:
            if val_result['violations']:
                summary_content += f"\n- **{val_result['test_name']}**: "
                summary_content += "; ".join(val_result['violations'])
    else:
        summary_content += """
### ✅ 全テスト合格

**次のステップ:**
1. Visualizer で3D可視化ツールを実装
2. フェーズ6 (統合テスト) へ進む

"""
    
    # ファイル出力
    summary_file = project_root / 'supervisor' / 'validation_summary.md'
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    print(f"✅ {summary_file} を生成しました")
    print(f"   合格: {passed_tests}/{len(validation_results)}")
    print(f"   不合格: {failed_tests}/{len(validation_results)}")
    
    return True

if __name__ == "__main__":
    print("🔍 Supervisor: 制約バリデーションサマリー生成\n")
    generate_validation_summary()
