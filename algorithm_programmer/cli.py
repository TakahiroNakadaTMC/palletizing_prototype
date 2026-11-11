#!/usr/bin/env python3
"""
パレタイザー実行CLI (cli.py)
指定したテストケースJSONを実行し、結果を出力します。
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
sys.path.insert(0, PROJECT_ROOT)

from algorithm_programmer.models import BoxSpec, PalletSpec
from algorithm_programmer.palletizer import Palletizer
from box_research.database_validation import STANDARD_PALLET_ID
from box_research.catalog_store import catalog_pallets, load_catalog, validate_staged_cases
from algorithm_programmer.catalog import run_catalog_case


def resolve_box_specs(
    box_list: Any,
    box_database: Dict[str, Any],
    lid_database: Dict[str, Any],
) -> Tuple[Dict[Tuple[str, str], BoxSpec], List[Dict[str, Any]]]:
    """テストケースに選ばれた箱・蓋だけを計算用仕様に変換する。"""
    if not isinstance(box_list, list):
        raise ValueError("テストケースの box_list はリスト形式で指定してください")
    if not isinstance(box_database, dict) or not isinstance(lid_database, dict):
        raise ValueError("箱DBと蓋DBはオブジェクト形式で指定してください")

    default_lid_id = next(
        (lid_id for lid_id, record in lid_database.items()
         if isinstance(record, dict) and record.get("type") == "NONE"),
        None,
    )
    selected_specs: Dict[Tuple[str, str], BoxSpec] = {}
    resolved_box_list: List[Dict[str, Any]] = []

    for index, item in enumerate(box_list):
        if not isinstance(item, dict):
            raise ValueError(f"box_list[{index}] はオブジェクト形式で指定してください")
        box_id = item.get("box_id")
        if not isinstance(box_id, str):
            raise ValueError(f"box_list[{index}] に有効な box_id がありません")

        resolved_item = dict(item)
        box_record = box_database.get(box_id)
        if box_record is None:
            if "lid_id" not in resolved_item and default_lid_id is not None:
                resolved_item["lid_id"] = default_lid_id
            resolved_box_list.append(resolved_item)
            continue
        if not isinstance(box_record, dict):
            raise ValueError(f"箱DBのレコードが不正です: {box_id}")

        lid_id = item.get("lid_id", default_lid_id)
        if not isinstance(lid_id, str) or lid_id not in lid_database:
            raise ValueError(f"蓋DBに選択された蓋がありません: {lid_id}")
        lid_record = lid_database[lid_id]
        if not isinstance(lid_record, dict):
            raise ValueError(f"蓋DBのレコードが不正です: {lid_id}")
        compatible_lids = box_record.get("compatible_lids", [])
        if (lid_record.get("type") != "NONE"
                and (not isinstance(compatible_lids, list) or lid_id not in compatible_lids)):
            raise ValueError(f"選択した蓋は箱に対応していません: {box_id}/{lid_id}")

        key = (box_id, lid_id)
        if key not in selected_specs:
            spec = BoxSpec.from_dict(box_record)
            spec.lid_id = lid_id
            spec.lid_width = float(lid_record.get("width", 0.0))
            spec.lid_length = float(lid_record.get("length", 0.0))
            spec.lid_thickness = float(lid_record.get("thickness", 0.0))
            spec.lid_fit_type = lid_record.get("fit_type", "なし")
            selected_specs[key] = spec

        resolved_item["lid_id"] = lid_id
        resolved_box_list.append(resolved_item)

    return selected_specs, resolved_box_list


def resolve_pallet_spec(
    tc_data: Dict[str, Any], pallet_database: Dict[str, Any]
) -> PalletSpec:
    """選択されたマスタレコードからパレット本体寸法を解決する。"""
    pallet_id = tc_data.get("pallet_id")
    pallets = pallet_database.get("pallets") if isinstance(pallet_database, dict) else None
    if not isinstance(pallet_id, str) or not isinstance(pallets, dict) or pallet_id not in pallets:
        raise ValueError("テストケースに有効な pallet_id がありません")

    pallet_record = pallets[pallet_id]
    if not isinstance(pallet_record, dict):
        raise ValueError(f"パレットDBのレコードが不正です: {pallet_id}")
    if pallet_id != STANDARD_PALLET_ID:
        supplier_name = tc_data.get("supplier_name")
        if not isinstance(supplier_name, str) or supplier_name not in pallet_record.get("suppliers", []):
            raise ValueError(f"仕入先とパレット型番が一致しません: {pallet_id}")

    case_pallet = tc_data.get("pallet", {})
    if not isinstance(case_pallet, dict):
        raise ValueError("テストケースの pallet はオブジェクト形式で指定してください")
    pallet_spec_data = {
        **case_pallet,
        "length": pallet_record.get("length"),
        "width": pallet_record.get("width"),
        "height": pallet_record.get("height"),
    }
    return PalletSpec.from_dict(pallet_spec_data)


def main():
    parser = argparse.ArgumentParser(description="パレタイザー実行CLI")
    parser.add_argument("testcase", nargs="?", help="実行する旧形式または品番方式のケースJSON")
    parser.add_argument("--catalog-case", help="品番DBに保存済みのケース名")
    parser.add_argument("--box-db", default=os.path.join(PROJECT_ROOT, "box_research", "box_db.json"), help="箱DBのJSONパス")
    parser.add_argument("--output", "-o", default=None, help="結果を出力するJSONパス")
    args = parser.parse_args()

    if bool(args.testcase) == bool(args.catalog_case):
        parser.error("ケースJSONまたは--catalog-caseのいずれか1つを指定してください")
    try:
        catalog = None
        if args.catalog_case:
            catalog, revision = load_catalog(Path(PROJECT_ROOT))
            if "cases" not in catalog or args.catalog_case not in catalog["cases"]["test_cases"]:
                raise ValueError("品番方式の保存済みケースがありません: " + args.catalog_case)
            tc_data = catalog["cases"]["test_cases"][args.catalog_case]
        else:
            with open(args.testcase, "r", encoding="utf-8-sig") as source:
                tc_data = json.load(source)
        if not isinstance(tc_data, dict):
            raise ValueError("ケースはオブジェクト形式で指定してください")
        box_list = tc_data.get("box_list", [])
        if not isinstance(box_list, list) or any(not isinstance(row, dict) for row in box_list):
            raise ValueError("box_listは箱行オブジェクトの配列で指定してください")
        part_mode = bool(args.catalog_case) or any("part_number" in row for row in box_list)
        test_name = tc_data.get("name", args.catalog_case or Path(args.testcase).stem)
        if part_mode:
            if args.box_db != parser.get_default("box_db"):
                raise ValueError("品番方式では--box-dbを併用できません")
            if args.output:
                output_path = Path(args.output).resolve()
                old_results = Path(PROJECT_ROOT) / "tester" / "results"
                if old_results.resolve() in output_path.parents or output_path == old_results.resolve():
                    raise ValueError("品番方式は旧結果フォルダへ保存できません")
            if catalog is None:
                catalog, revision = load_catalog(Path(PROJECT_ROOT))
            pallets = catalog_pallets(Path(PROJECT_ROOT))
            validate_staged_cases({
                "schema_version": 1, "test_cases": {test_name: tc_data},
                "approval_state": {test_name: True},
            }, catalog["parts"], pallets)
            pallet_spec = resolve_pallet_spec(tc_data, pallets)
            result_dict = run_catalog_case(test_name, tc_data, catalog, pallet_spec, revision)
        else:
            with open(args.box_db, "r", encoding="utf-8") as source:
                box_database = json.load(source)
            with open(os.path.join(PROJECT_ROOT, "box_research", "lid_db.json"),
                      "r", encoding="utf-8") as source:
                lid_database = json.load(source)
            with open(os.path.join(PROJECT_ROOT, "box_research", "pallet_db.json"),
                      "r", encoding="utf-8") as source:
                pallet_database = json.load(source)
            pallet_spec = resolve_pallet_spec(tc_data, pallet_database)
            box_specs, resolved_box_list = resolve_box_specs(box_list, box_database, lid_database)
            result_dict = Palletizer(box_specs, pallet_spec).run(test_name, resolved_box_list).to_dict()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        parser.exit(1, "パレタイズ実行エラー: {}\n".format(error))

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
    print(f"  パレット込み総高さ: {summary['total_height']:.1f}mm")
    if result_dict.get("input_mode") == "part_number":
        print(f"  計算方式: {result_dict['algorithm_mode']} / 品番配分: 入力順（平準化なし）")
        for item in result_dict["part_counts"]:
            print(f"  品番 {item['part_number']} ({item['box_name']}): "
                  f"配置 {item['placed_count']}/{item['input_count']}箱 / 未配置 {item['unplaced_count']}箱")
        for item in result_dict["unplaced_boxes"]:
            print(f"  未配置理由 {item['part_number']}: {item['reason']}")
    for warning in summary["warnings"]:
        print(f"  警告: {warning}")
    if not summary["is_valid"]:
        for v in summary["violations"]:
            print(f"    - 違反: {v}")
        if part_mode:
            parser.exit(1)

if __name__ == "__main__":
    main()
