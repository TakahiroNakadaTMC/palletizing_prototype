#!/usr/bin/env python3
"""品番方式ケースの一括実行ランナー。"""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "tester" / "catalog_results"


def _timestamped_output_dir(base_dir: Path) -> Path:
    stem = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base_dir / stem
    suffix = 1
    while candidate.exists():
        candidate = base_dir / f"{stem}_{suffix:02d}"
        suffix += 1
    return candidate


def _save_result_atomic(path: Path, payload: dict) -> None:
    with tempfile.NamedTemporaryFile(
        dir=str(path.parent), mode="w", encoding="utf-8", delete=False, suffix=".tmp"
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            json.dump(payload, temporary, ensure_ascii=False, indent=2, allow_nan=False)
        except (TypeError, ValueError, OSError):
            temporary.close()
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        os.replace(str(temporary_path), str(path))
    finally:
        temporary_path.unlink(missing_ok=True)


def run_catalog_tests(output_dir: Optional[Path] = None) -> int:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from algorithm_programmer.catalog import run_catalog_case
    from algorithm_programmer.cli import resolve_pallet_spec
    from box_research.catalog_store import catalog_pallets, load_catalog

    root = PROJECT_ROOT
    data, revision = load_catalog(root)
    if "cases" not in data:
        raise ValueError("品番方式の保存済みケースがありません")

    selected = [
        (name, case)
        for name, case in data["cases"]["test_cases"].items()
        if data["cases"]["approval_state"].get(name) is True
    ]
    if not selected:
        raise ValueError("品番方式の採用済みケースがありません")

    output_dir = (output_dir or _timestamped_output_dir(DEFAULT_RESULTS_ROOT)).resolve()
    legacy_results = (PROJECT_ROOT / "tester" / "results").resolve()
    if output_dir == legacy_results or legacy_results in output_dir.parents:
        raise ValueError("旧方式の結果フォルダ(tester/results)は指定できません")
    output_dir.mkdir(parents=True, exist_ok=False)
    pallets = catalog_pallets(root, data["pallets"])

    rows = []
    started_at = datetime.now().isoformat(timespec="seconds")
    print(f"結果フォルダ: {output_dir}")
    for name, case in selected:
        start = time.monotonic()
        try:
            result = run_catalog_case(name, case, data, resolve_pallet_spec(case, pallets), revision)
            path = output_dir / ("result_" + name + ".json")
            _save_result_atomic(path, result)
            status = "PASS" if result["summary"]["is_valid"] else "FAIL"
            row = dict(
                name=name,
                status=status,
                input=result["input_boxes_count"],
                placed=result["placed_boxes_count"],
                unplaced=result["unplaced_boxes_count"],
                violations=result["summary"]["violations"],
                result_file=path.name,
            )
            print(f"{status} [{name}]: {row['placed']}/{row['input']}箱 / 未配置{row['unplaced']}箱")
        except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
            row = dict(name=name, status="ERROR", error=str(error))
            print(f"ERROR [{name}]: {error}", file=sys.stderr)
        row["elapsed_seconds"] = round(time.monotonic() - start, 3)
        rows.append(row)

    counts = dict(
        cases=len(rows),
        passed=sum(row["status"] == "PASS" for row in rows),
        failed=sum(row["status"] == "FAIL" for row in rows),
        errors=sum(row["status"] == "ERROR" for row in rows),
        input=sum(row.get("input", 0) for row in rows),
        placed=sum(row.get("placed", 0) for row in rows),
        unplaced=sum(row.get("unplaced", 0) for row in rows),
    )
    manifest = dict(
        input_mode="part_number",
        source="catalog_store",
        catalog_revision=revision,
        started_at=started_at,
        completed_at=datetime.now().isoformat(timespec="seconds"),
        counts=counts,
        cases=rows,
    )
    _save_result_atomic(output_dir / "run_manifest.json", manifest)
    print(json.dumps(counts, ensure_ascii=False))
    return 1 if counts["failed"] or counts["errors"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="採用済み品番ケースの一括実行")
    parser.add_argument("--output-dir", type=Path, help="結果出力フォルダ（省略時は時刻名で新規作成）")
    args = parser.parse_args()
    try:
        sys.exit(run_catalog_tests(args.output_dir))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "品番方式の一括実行エラー: {}\n".format(error))
