#!/usr/bin/env python3
"""
テスト一括実行スクリプト (run_tests.py)
test_programmer/test_cases/ 配下の全テストケースを実行し、
tester/results/ にパレタイズ結果JSONを出力します。
"""

import os
import sys
import glob
import json
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TEST_CASES_DIR = os.path.join(PROJECT_ROOT, "test_programmer", "test_cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tester", "results")

def run_all_tests():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    tc_files = sorted(glob.glob(os.path.join(TEST_CASES_DIR, "*.json")))

    if not tc_files:
        print("❌ テストケースが見つかりません。先に generate_testcases.py を実行してください。")
        return

    print(f"🧪 {len(tc_files)} 件のテストケースを実行します...\n")

    summary_list = []

    for tc_path in tc_files:
        tc_name = os.path.basename(tc_path).replace(".json", "")
        out_path = os.path.join(RESULTS_DIR, f"result_{tc_name}.json")

        cmd = [
            sys.executable,
            os.path.join(PROJECT_ROOT, "algorithm_programmer", "cli.py"),
            tc_path,
            "-o",
            out_path
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"❌ エラー ({tc_name}): {res.stderr}")
            continue

        try:
            with open(out_path, "r", encoding="utf-8") as f:
                rdata = json.load(f)
            s = rdata.get("summary", {})
            bbox = s.get("bounding_box", {})
            status = "✅ PASS" if s.get("is_valid") else "❌ FAIL"
            summary_list.append({
                "name": tc_name,
                "status": status,
                "boxes": len(rdata.get("boxes", [])),
                "layers": s.get("total_layers", 0),
                "vol": s.get("volume_efficiency_percent", 0.0),
                "x_span": bbox.get("x_span", 0.0),
                "y_span": bbox.get("y_span", 0.0),
                "z_max": bbox.get("max_z", 0.0),
                "violations": s.get("violations", [])
            })
            print(f"  {status} [{tc_name}]: {len(rdata.get('boxes', []))}箱, 充填率 {s.get('volume_efficiency_percent', 0.0):.1f}%, X={bbox.get('x_span', 0.0):.0f} Y={bbox.get('y_span', 0.0):.0f} Z={bbox.get('max_z', 0.0):.0f}")
        except Exception as e:
            print(f"❌ 結果読み込み失敗 ({tc_name}): {e}")

    print("\n" + "="*80)
    print("📊 テスト実行サマリー一覧")
    print("="*80)
    print(f"{'テストケース名':<30} | {'状態':<6} | {'箱数':<4} | {'段数':<3} | {'充填率':<6} | {'荷姿 (X × Y × Z mm)'}")
    print("-"*80)
    for row in summary_list:
        dims = f"{row['x_span']:.0f} × {row['y_span']:.0f} × {row['z_max']:.0f}"
        print(f"{row['name']:<30} | {row['status']:<6} | {row['boxes']:<4} | {row['layers']:<3} | {row['vol']:>5.1f}% | {dims}")
    print("="*80)

if __name__ == "__main__":
    run_all_tests()
