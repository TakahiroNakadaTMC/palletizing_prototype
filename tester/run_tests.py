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
import argparse
from pathlib import Path
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TEST_CASES_DIR = os.path.join(PROJECT_ROOT, "test_programmer", "test_cases")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "tester", "results")
APPROVAL_STATE_PATH = os.path.join(PROJECT_ROOT, "test_programmer", "test_case_approval.json")

def load_approval_state():
    if not os.path.exists(APPROVAL_STATE_PATH):
        return None

    with open(APPROVAL_STATE_PATH, "r", encoding="utf-8") as f:
        approval_state = json.load(f)
    if not isinstance(approval_state, dict):
        raise ValueError("test_case_approval.json must contain an object")
    return approval_state

def select_approved_cases(test_case_paths, approval_state):
    if approval_state is None:
        return list(test_case_paths)

    return [
        path for path in test_case_paths
        if approval_state.get(os.path.basename(path)[:-5]) is True
    ]


def run_catalog_tests(output_dir: Path) -> int:
    """品番方式だけを別フォルダへ実行し、今回の結果一覧を残す。"""
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    from algorithm_programmer.catalog import run_catalog_case
    from algorithm_programmer.cli import resolve_pallet_spec
    from box_research.catalog_store import catalog_pallets, load_catalog

    root = Path(PROJECT_ROOT)
    data, revision = load_catalog(root)
    if "cases" not in data:
        raise ValueError("品番方式の保存済みケースがありません")
    selected = [(name, case) for name, case in data["cases"]["test_cases"].items()
                if data["cases"]["approval_state"][name]]
    if not selected:
        raise ValueError("品番方式の採用済みケースがありません")
    output_dir = output_dir.resolve()
    legacy_results = (root / "tester" / "results").resolve()
    if output_dir == legacy_results or legacy_results in output_dir.parents:
        raise ValueError("品番方式は旧結果フォルダへ保存できません")
    output_dir.mkdir(parents=True, exist_ok=False)
    pallets = catalog_pallets(root)
    rows = []
    for name, case in selected:
        start = time.monotonic()
        try:
            result = run_catalog_case(name, case, data, resolve_pallet_spec(case, pallets), revision)
            path = output_dir / ("result_" + name + ".json")
            with tempfile.NamedTemporaryFile(dir=str(output_dir), mode="w", encoding="utf-8",
                                             delete=False, suffix=".tmp") as temporary:
                temporary_path = Path(temporary.name)
                try:
                    json.dump(result, temporary, ensure_ascii=False, indent=2, allow_nan=False)
                except (TypeError, ValueError, OSError):
                    temporary.close()
                    temporary_path.unlink()
                    raise
            try:
                os.replace(str(temporary_path), str(path))
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
            status = "PASS" if result["summary"]["is_valid"] else "FAIL"
            row = dict(name=name, status=status, input=result["input_boxes_count"],
                       placed=result["placed_boxes_count"], unplaced=result["unplaced_boxes_count"],
                       violations=result["summary"]["violations"], result_file=path.name)
            print(f"{status} [{name}]: {row['placed']}/{row['input']}箱 / 未配置{row['unplaced']}箱")
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
            row = dict(name=name, status="ERROR", error=str(error))
            print(f"ERROR [{name}]: {error}", file=sys.stderr)
        row["elapsed_seconds"] = round(time.monotonic() - start, 3)
        rows.append(row)
    counts = dict(cases=len(rows), passed=sum(row["status"] == "PASS" for row in rows),
                  failed=sum(row["status"] == "FAIL" for row in rows),
                  errors=sum(row["status"] == "ERROR" for row in rows),
                  input=sum(row.get("input", 0) for row in rows),
                  placed=sum(row.get("placed", 0) for row in rows),
                  unplaced=sum(row.get("unplaced", 0) for row in rows))
    with (output_dir / "run_manifest.json").open("w", encoding="utf-8") as target:
        json.dump(dict(input_mode="part_number", catalog_revision=revision, counts=counts, cases=rows),
                  target, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(counts, ensure_ascii=False))
    return 1 if counts["failed"] or counts["errors"] else 0


def run_all_tests():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    all_tc_files = sorted(glob.glob(os.path.join(TEST_CASES_DIR, "*.json")))

    if not all_tc_files:
        print("❌ テストケースが見つかりません。先に generate_testcases.py を実行してください。")
        return 1

    approval_state = load_approval_state()
    tc_files = select_approved_cases(all_tc_files, approval_state)
    skipped_count = len(all_tc_files) - len(tc_files)

    if not tc_files:
        print(f"⚠️ 採用済みのテストケースがありません（未採用: {skipped_count} 件）。")
        return 1

    print(f"🧪 {len(tc_files)} 件の採用済みテストケースを実行します（除外: {skipped_count} 件）...\n")

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

        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
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
                "input": rdata.get("input_boxes_count", 0),
                "unplaced": rdata.get("unplaced_boxes_count", 0),
                "warnings": s.get("warnings", []),
                "violations": s.get("violations", [])
            })
            print(f"  {status} [{tc_name}]: {len(rdata.get('boxes', []))}箱, 充填率 {s.get('volume_efficiency_percent', 0.0):.1f}%, X={bbox.get('x_span', 0.0):.0f} Y={bbox.get('y_span', 0.0):.0f} Z={bbox.get('max_z', 0.0):.0f}")
            print(f"    投入: {rdata.get('input_boxes_count', 0)}箱 / 未配置: {rdata.get('unplaced_boxes_count', 0)}箱")
            for warning in s.get("warnings", []):
                print(f"    ⚠️ {warning}")
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
    print(f"結果読込: {len(summary_list)}/{len(tc_files)}件 | "
          f"投入: {sum(row['input'] for row in summary_list)}箱 / "
          f"配置: {sum(row['boxes'] for row in summary_list)}箱 / "
          f"未配置: {sum(row['unplaced'] for row in summary_list)}箱")
    print(f"はみ出し要確認: {sum(bool(row['warnings']) for row in summary_list)}件（制約合否とは別）")
    print("="*80)
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="採用済みケースの一括実行")
    parser.add_argument("--catalog", action="store_true", help="品番方式の保存済みケースを実行")
    parser.add_argument("--output-dir", type=Path, help="品番方式の新規結果フォルダ")
    args = parser.parse_args()
    if args.catalog:
        if args.output_dir is None:
            parser.error("--catalogでは--output-dirに未使用のフォルダを指定してください")
        try:
            sys.exit(run_catalog_tests(args.output_dir))
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.exit(1, "品番方式の一括実行エラー: {}\n".format(error))
    if args.output_dir is not None:
        parser.error("--output-dirは--catalogと併用してください")
    sys.exit(run_all_tests())
