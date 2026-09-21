#!/usr/bin/env python3
"""
テストケース生成スクリプト (generate_testcases.py)
box_research/box_db.json に登録・承認された箱データに基づき、
単載・同高混載・異高モジュール混載・境界値テスト用のテストケースJSON群を自動生成します。
"""

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
BOX_DB_PATH = os.path.join(PROJECT_ROOT, "box_research", "box_db.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "test_cases")

PALLET_SPEC = {
    "width": 1200.0,
    "length": 1000.0,
    "max_height": 1200.0,
    "max_x_span": 1360.0,
    "min_y_span": 800.0,
    "max_y_span": 1100.0
}

def load_box_db():
    with open(BOX_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_test_cases():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    box_db = load_box_db()
    available_ids = list(box_db.keys())
    print(f"📦 利用可能な承認済み箱 ({len(available_ids)} 種類): {available_ids}")

    test_cases = {}

    # -------------------------------------------------------------
    # 1. 単載テストケース (Single-type test cases)
    # -------------------------------------------------------------
    # (1) TP-332 基準モジュール標準型 (335x335x195)
    if "TP-332" in box_db:
        test_cases["single_tp332"] = {
            "name": "single_tp332",
            "description": "TP-332 (335x335x195) 基準モジュール標準型の単載テスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-332", "count": 60}
            ]
        }

    # (2) TP-342 1.5モジュール標準型 (503x335x195)
    if "TP-342" in box_db:
        test_cases["single_tp342"] = {
            "name": "single_tp342",
            "description": "TP-342 (503x335x195) 1.5モジュール標準型の単載テスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-342", "count": 40}
            ]
        }

    # (3) TP-362 2倍モジュール標準型 (670x335x195) - 長辺1340mmフィット検証
    if "TP-362" in box_db:
        test_cases["single_tp362"] = {
            "name": "single_tp362",
            "description": "TP-362 (670x335x195) 2倍モジュールの単載（長辺1340mmフィット）テスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-362", "count": 30}
            ]
        }

    # (4) TP-462 大型モジュール標準型 (670x503x195)
    if "TP-462" in box_db:
        test_cases["single_tp462"] = {
            "name": "single_tp462",
            "description": "TP-462 (670x503x195) 大型モジュール標準型の単載テスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-462", "count": 24}
            ]
        }

    # (5) TP-131 ハーフモジュール浅型 (335x168x103)
    if "TP-131" in box_db:
        test_cases["single_tp131"] = {
            "name": "single_tp131",
            "description": "TP-131 (335x168x103) ハーフモジュール浅型の単載テスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-131", "count": 120}
            ]
        }

    # (6) TP-331 基準モジュール浅型 (335x335x103)
    if "TP-331" in box_db:
        test_cases["single_tp331"] = {
            "name": "single_tp331",
            "description": "TP-331 (335x335x103) 基準モジュール浅型の単載テスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-331", "count": 80}
            ]
        }

    # -------------------------------------------------------------
    # 2. モジュール混載テストケース (Modular mixed test cases)
    # -------------------------------------------------------------
    # (7) mixed_tp_same_height: 同一高さ (H=195mm) のTPモジュール混載
    mixed_same_h_boxes = []
    for bid, cnt in [("TP-332", 16), ("TP-342", 12), ("TP-362", 8), ("TP-462", 6)]:
        if bid in box_db:
            mixed_same_h_boxes.append({"box_id": bid, "count": cnt})
    if mixed_same_h_boxes:
        test_cases["mixed_tp_same_height"] = {
            "name": "mixed_tp_same_height",
            "description": "同一高さ（H=195mm: TP-332, 342, 362, 462）のTPモジュール混載テスト",
            "pallet": PALLET_SPEC,
            "box_list": mixed_same_h_boxes
        }

    # (8) mixed_tp_modular_stack: 基準箱と2倍箱のモジュール段積み混載
    modular_stack_boxes = []
    for bid, cnt in [("TP-331", 24), ("TP-332", 18), ("TP-362", 10), ("TP-462", 6)]:
        if bid in box_db:
            modular_stack_boxes.append({"box_id": bid, "count": cnt})
    if modular_stack_boxes:
        test_cases["mixed_tp_modular_stack"] = {
            "name": "mixed_tp_modular_stack",
            "description": "TP-331/332とTP-362/462のモジュール倍数関係を活用した段積み混載テスト",
            "pallet": PALLET_SPEC,
            "box_list": modular_stack_boxes
        }

    # (9) mixed_tp_different_heights: 異高混載 (103, 149, 195, 288mm)
    diff_h_boxes = []
    for bid, cnt in [
        ("TP-131", 16), ("TP-331", 12), ("TP-331.5", 12),
        ("TP-341.5", 8), ("TP-342", 8), ("TP-343", 6),
        ("TP-362", 4), ("TP-363", 4), ("TP-463", 4)
    ]:
        if bid in box_db:
            diff_h_boxes.append({"box_id": bid, "count": cnt})
    if diff_h_boxes:
        test_cases["mixed_tp_different_heights"] = {
            "name": "mixed_tp_different_heights",
            "description": "4種類の高さ（103, 149, 195, 288mm）が混在する高度な混載テスト",
            "pallet": PALLET_SPEC,
            "box_list": diff_h_boxes
        }

    # (10) mixed_tp_large_volume: 大量投入・上限パッキングテスト
    large_vol_boxes = []
    for bid in available_ids:
        large_vol_boxes.append({"box_id": bid, "count": 10})
    test_cases["mixed_tp_large_volume"] = {
        "name": "mixed_tp_large_volume",
        "description": "全承認箱種（各10箱）を大量投入し、最大積載高1200mmまで充填する混載テスト",
        "pallet": PALLET_SPEC,
        "box_list": large_vol_boxes
    }

    # -------------------------------------------------------------
    # 3. 境界値・制約検証テストケース (Boundary & Constraint test cases)
    # -------------------------------------------------------------
    # (11) boundary_height_limit: 深型（H=288mm）による積載高さ1200mm境界値テスト
    # 288 + 3*(288-10) = 288 + 834 = 1122mm <= 1200mm (4段積載可能)
    deep_boxes = []
    for bid in ["TP-333", "TP-343", "TP-363", "TP-463"]:
        if bid in box_db:
            deep_boxes.append({"box_id": bid, "count": 12})
    if deep_boxes:
        test_cases["boundary_height_limit"] = {
            "name": "boundary_height_limit",
            "description": "深型（H=288mm）のみで4段積載（総高1122mm）を行う高さ制約境界値テスト",
            "pallet": PALLET_SPEC,
            "box_list": deep_boxes
        }

    # (12) boundary_overhang_long_side: TP-362/363(長辺670)を2列並べて1340mmのオーバーハングを検証
    if "TP-362" in box_db and "TP-363" in box_db:
        test_cases["boundary_overhang_long_side"] = {
            "name": "boundary_overhang_long_side",
            "description": "長辺670mm箱を2列配置し、長辺荷姿1340mm（<1360mm許容枠）を検証するテスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-362", "count": 18},
                {"box_id": "TP-363", "count": 12}
            ]
        }

    # (13) boundary_min_short_side: 短辺荷姿が800mm〜1000mmを満たすかの検証
    if "TP-342" in box_db and "TP-332" in box_db:
        test_cases["boundary_min_short_side"] = {
            "name": "boundary_min_short_side",
            "description": "短辺方向が800mm以上1000mm以下の制約を満たしているかを検証するテスト",
            "pallet": PALLET_SPEC,
            "box_list": [
                {"box_id": "TP-342", "count": 16},
                {"box_id": "TP-332", "count": 16}
            ]
        }

    # JSONファイルへ書き出し
    created_files = []
    for tc_name, tc_data in test_cases.items():
        file_path = os.path.join(OUTPUT_DIR, f"{tc_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(tc_data, f, ensure_ascii=False, indent=2)
        created_files.append(file_path)
        print(f"  ✓ 生成: {os.path.basename(file_path)} ({tc_data['description']})")

    print(f"\n✨ 合計 {len(created_files)} 件のテストケースJSONを生成しました: {OUTPUT_DIR}")
    return test_cases

if __name__ == "__main__":
    generate_test_cases()
