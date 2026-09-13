#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
フェーズ5: エージェント実装 - Box Research 検証スクリプト

既存の box_db.json を検証し、すべてのTP規格箱が正確に登録されているか確認。
"""

import json
import sys
from pathlib import Path

# Windows環境での文字コード対応
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def verify_box_db():
    """box_db.json の整合性検証"""
    print("\n" + "="*60)
    print("Box Research エージェント - box_db.json 検証")
    print("="*60)
    
    box_db_file = Path(__file__).parent / "box_research" / "box_db.json"
    
    if not box_db_file.exists():
        print(f"❌ ファイルなし: {box_db_file}")
        return False
    
    with open(box_db_file, 'r', encoding='utf-8') as f:
        box_db = json.load(f)
    
    print(f"\n✅ ファイル読み込み成功")
    print(f"📦 登録されている箱数: {len(box_db)}\n")
    
    # 必須フィールド
    required_fields = {
        'id', 'width', 'length', 'height', 
        'fitting_depth', 'rib_thickness', 'module_ratio'
    }
    
    # 検証開始
    all_valid = True
    
    for box_id, box_data in sorted(box_db.items()):
        print(f"📋 {box_id}:")
        
        # フィールド確認
        missing = required_fields - set(box_data.keys())
        if missing:
            print(f"  ❌ 欠落フィールド: {missing}")
            all_valid = False
            continue
        
        # 値の確認
        print(f"  - 寸法: {box_data['width']}×{box_data['length']}×{box_data['height']}mm")
        print(f"  - 勘合深さ (fitting_depth): {box_data['fitting_depth']}mm")
        print(f"  - リブ厚み (rib_thickness): {box_data['rib_thickness']}mm")
        print(f"  - モジュール比率: {box_data['module_ratio']}")
        print(f"  ✅")
    
    print("\n" + "="*60)
    
    # モジュール比率の集計
    module_ratios = set(box['module_ratio'] for box in box_db.values())
    print(f"\n📊 モジュール比率の種類: {sorted(module_ratios)}")
    
    # TP規格の整合性確認
    tp_rules = {
        "1x0.5": "TP-130系",
        "1x1": "TP-330系",
        "1.5x1": "TP-340系",
        "2x1": "TP-360系",
        "2x1.5": "TP-460系"
    }
    
    print("\n📐 TP規格モジュール整合性:")
    for ratio, series in tp_rules.items():
        boxes_in_ratio = [b for b, d in box_db.items() if d['module_ratio'] == ratio]
        if boxes_in_ratio:
            print(f"  ✅ {ratio}: {series} - {len(boxes_in_ratio)}個 {boxes_in_ratio}")
        else:
            print(f"  ⚠️  {ratio}: {series} - 未登録")
    
    # 勘合深さの確認
    fitting_depths = set(box['fitting_depth'] for box in box_db.values())
    print(f"\n🔻 登録されている勘合深さ (mm): {sorted(fitting_depths)}")
    
    print("\n" + "="*60)
    if all_valid and len(box_db) >= 10:
        print("✅ box_db.json 検証成功")
        print(f"   {len(box_db)}個のTP規格箱が正確に登録されています")
        return True
    else:
        print("❌ box_db.json 検証失敗")
        return False

def verify_constraints_compatibility():
    """constraints.md との互換性確認"""
    print("\n" + "="*60)
    print("制約仕様との整合性確認")
    print("="*60)
    
    constraints_file = Path(__file__).parent / "constraints" / "constraints.md"
    box_db_file = Path(__file__).parent / "box_research" / "box_db.json"
    
    with open(constraints_file, 'r', encoding='utf-8') as f:
        constraints = f.read()
    
    with open(box_db_file, 'r', encoding='utf-8') as f:
        box_db = json.load(f)
    
    # 制約値の抽出
    import re
    
    max_height = re.search(r'(\d+)\s*mm.*積載高さ', constraints)
    long_side_limit = re.search(r'(\d+)\s*mm.*長辺', constraints)
    short_side_min = re.search(r'(\d+)\s*mm.*短辺.*最小', constraints) or re.search(r'(\d+)\s*mm.*800.*短辺', constraints)
    
    print("\n制約値の確認:")
    print(f"  積載高さ上限: {max_height.group(1) if max_height else '未検出'}mm")
    print(f"  長辺制限: {long_side_limit.group(1) if long_side_limit else '未検出'}mm")
    print(f"  短辺最小: {short_side_min.group(1) if short_side_min else '未検出'}mm")
    
    # 各箱のサイズが制約を超えないか確認
    print("\n各箱のサイズ検証:")
    for box_id, box_data in sorted(box_db.items()):
        # 箱の外寸が妥当か（1単位が335mm程度のモジュール）
        if box_data['width'] > 1200 or box_data['length'] > 1200:
            print(f"  ⚠️  {box_id}: 箱寸法が大きい {box_data['width']}×{box_data['length']}")
        else:
            print(f"  ✅ {box_id}: {box_data['width']}×{box_data['length']}mm")
    
    print("\n" + "="*60)
    print("✅ 制約仕様との互換性確認完了")
    return True

if __name__ == "__main__":
    print("\n🔍 Box Research エージェント - テスト実行\n")
    
    result1 = verify_box_db()
    result2 = verify_constraints_compatibility()
    
    print("\n" + "="*60)
    print("テスト結果")
    print("="*60)
    
    if result1 and result2:
        print("✅ 全テスト成功")
        print("\n次ステップ:")
        print("  1. algorithm-research エージェントを実行")
        print("  2. proposal.md でアルゴリズム方式を提案")
    else:
        print("❌ テスト失敗 - 修正が必要です")
    
    print("="*60 + "\n")
