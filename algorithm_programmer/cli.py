#!/usr/bin/env python3
"""
パレタイザー実行CLI (cli.py)
指定したテストケースJSONを実行し、結果を出力します。
"""

import sys
import os
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

from algorithm_programmer.models import BoxSpec, PalletSpec
from algorithm_programmer.palletizer import Palletizer

def main():
    parser = argparse.ArgumentParser(description="パレタイザー実行CLI")
    parser.add_argument("testcase", help="実行するテストケースJSONのパス")
    parser.add_argument("--box-db", default=os.path.join(PROJECT_ROOT, "box_research", "box_db.json"), help="箱DBのJSONパス")
    parser.add_argument("--output", "-o", default=None, help="結果を出力するJSONパス")
    args = parser.parse_args()

    # 1. 箱DBのロード
    with open(args.box_db, "r", encoding="utf-8") as f:
        raw_db = json.load(f)
    box_db = {bid: BoxSpec.from_dict(bdata) for bid, bdata in raw_db.items()}

    # 2. テストケースのロード
    with open(args.testcase, "r", encoding="utf-8") as f:
        tc_data = json.load(f)

    test_name = tc_data.get("name", os.path.basename(args.testcase).replace(".json", ""))
    pallet_spec = PalletSpec.from_dict(tc_data.get("pallet", {}))
    box_list = tc_data.get("box_list", [])

    # 3. パレタイズの実行
    palletizer = Palletizer(box_db, pallet_spec)
    result = palletizer.run(test_name, box_list)

    result_dict = result.to_dict()

    # 4. 出力
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2)
        print(f"✓ 結果を保存しました: {args.output}")
    else:
        print(json.dumps(result_dict, ensure_ascii=False, indent=2))

    summary = result_dict["summary"]
    print(f"\n--- 実行結果サマリー ({test_name}) ---")
    print(f"  配置箱数: {summary['total_boxes']} 箱 / 段数: {summary['total_layers']} 段")
    print(f"  荷姿寸法: X={summary['bounding_box']['x_span']:.1f}mm, Y={summary['bounding_box']['y_span']:.1f}mm, Z={summary['bounding_box']['max_z']:.1f}mm")
    print(f"  体積充填率: {summary['volume_efficiency_percent']:.1f}%")
    print(f"  制約合否: {'✅ PASS' if summary['is_valid'] else '❌ FAIL'}")
    if not summary["is_valid"]:
        for v in summary["violations"]:
            print(f"    - 違反: {v}")

if __name__ == "__main__":
    main()
