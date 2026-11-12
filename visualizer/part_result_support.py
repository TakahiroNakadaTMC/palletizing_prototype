"""Part-result validation and catalog-run discovery helpers for visualizer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

SUPPORTED_COORDINATE_REFERENCES = {
    "combined_footprint_min_xy_top_z",
}
RUN_MANIFEST_NAME = "run_manifest.json"
_KNOWN_STATUS = {"PASS", "FAIL", "ERROR"}


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as source:
            data = json.load(source)
    except OSError as error:
        raise ValueError(f"{path.name} を読み込めません: {error}") from error
    except ValueError as error:
        raise ValueError(f"{path.name} のJSON形式が不正です: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} のJSONはオブジェクト形式である必要があります")
    return data


def _is_non_negative_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_iso_datetime(value, *, label: str, errors: List[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} は空でないISO日時文字列で指定してください")
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} はISO日時形式で指定してください: {value}")
        return None


def validate_part_result_payload(data: dict, *, source: str = "結果JSON") -> None:
    if data.get("schema_version") != 2:
        raise ValueError(f"{source}: schema_version=2 が必要です")
    if data.get("input_mode") != "part_number":
        raise ValueError(f"{source}: input_mode='part_number' が必要です")
    coordinate_reference = data.get("coordinate_reference")
    if coordinate_reference not in SUPPORTED_COORDINATE_REFERENCES:
        allowed = ", ".join(sorted(SUPPORTED_COORDINATE_REFERENCES))
        raise ValueError(
            f"{source}: coordinate_reference は次のいずれかで指定してください: {allowed}"
        )
    for key in ("boxes", "part_counts", "unplaced_boxes"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"{source}: {key} は配列で指定してください")

    parts: Dict[str, dict] = {}
    for row in data["part_counts"]:
        if not isinstance(row, dict):
            raise ValueError(f"{source}: part_counts の要素が不正です")
        part_number = row.get("part_number")
        if not isinstance(part_number, str) or not part_number:
            raise ValueError(f"{source}: part_counts.part_number が不正です")
        if part_number in parts:
            raise ValueError(f"{source}: part_counts に重複品番があります ({part_number})")
        for key in ("supplier_name", "box_name", "box_model_id", "lid_id"):
            if not isinstance(row.get(key), str):
                raise ValueError(f"{source}: part_counts.{key} が不正です ({part_number})")
        for key in ("input_count", "placed_count", "unplaced_count"):
            value = row.get(key)
            if not _is_non_negative_int(value):
                raise ValueError(f"{source}: part_counts.{key} が不正です ({part_number})")
        if row["input_count"] != row["placed_count"] + row["unplaced_count"]:
            raise ValueError(f"{source}: part_counts 数量整合が不正です ({part_number})")
        parts[part_number] = {"row": row, "placed": 0, "unplaced": 0}

    def _accumulate(rows: List[dict], total_key: str, count_key: str | None) -> None:
        for box in rows:
            if not isinstance(box, dict):
                raise ValueError(f"{source}: 箱情報の要素が不正です")
            part_number = box.get("part_number")
            part = parts.get(part_number)
            if part is None:
                raise ValueError(f"{source}: 未登録品番が存在します ({part_number})")
            for key in ("supplier_name", "box_name", "box_model_id", "lid_id"):
                if box.get(key) != part["row"][key]:
                    raise ValueError(f"{source}: 品番メタデータが不一致です ({part_number})")
            if box.get("box_id") != box.get("box_name"):
                raise ValueError(f"{source}: box_id と box_name が不一致です ({part_number})")
            count = 1 if count_key is None else box.get(count_key)
            if not _is_non_negative_int(count) or count < 1:
                raise ValueError(f"{source}: 箱数量が不正です ({part_number})")
            part[total_key] += count

    _accumulate(data["boxes"], "placed", None)
    _accumulate(data["unplaced_boxes"], "unplaced", "count")

    total_input = 0
    total_placed = 0
    total_unplaced = 0
    for part_number, value in parts.items():
        if value["placed"] != value["row"]["placed_count"] or value["unplaced"] != value["row"]["unplaced_count"]:
            raise ValueError(f"{source}: 品番集計と箱一覧の数量が一致しません ({part_number})")
        total_input += value["row"]["input_count"]
        total_placed += value["placed"]
        total_unplaced += value["unplaced"]
    if total_input != data.get("input_boxes_count"):
        raise ValueError(f"{source}: input_boxes_count が品番集計と一致しません")
    if total_placed != data.get("placed_boxes_count"):
        raise ValueError(f"{source}: placed_boxes_count が品番集計と一致しません")
    if total_unplaced != data.get("unplaced_boxes_count"):
        raise ValueError(f"{source}: unplaced_boxes_count が品番集計と一致しません")


def load_part_results_from_manifest(results_dir: Path) -> List[dict]:
    manifest_path = results_dir / RUN_MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(
            f"{RUN_MANIFEST_NAME} が見つかりません: {results_dir} "
            "（catalog runner の出力フォルダを指定してください）"
        )
    manifest = _read_json(manifest_path)

    errors = []
    if manifest.get("input_mode") != "part_number":
        errors.append("input_mode='part_number' の実行のみ表示できます")
    if manifest.get("source") != "catalog_store":
        errors.append("source='catalog_store' の実行のみ表示できます")

    revision = manifest.get("catalog_revision")
    if not isinstance(revision, str) or not revision:
        errors.append("catalog_revision は空でない文字列で指定してください")

    started_at = _parse_iso_datetime(manifest.get("started_at"), label="started_at", errors=errors)
    completed_at = _parse_iso_datetime(manifest.get("completed_at"), label="completed_at", errors=errors)
    if started_at is not None and completed_at is not None and completed_at < started_at:
        errors.append("completed_at は started_at 以降である必要があります")

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts オブジェクトがありません")
        counts = {}
    for key in ("cases", "passed", "failed", "errors", "input", "placed", "unplaced"):
        if not _is_non_negative_int(counts.get(key)):
            errors.append(f"counts.{key} は0以上の整数で指定してください")

    cases = manifest.get("cases")
    if not isinstance(cases, list):
        errors.append("cases 配列がありません")
        cases = []
    if errors:
        raise ValueError(f"{manifest_path.name}: " + " / ".join(errors))

    entries = []
    row_errors = []
    seen_names = set()
    seen_files = set()
    passed = 0
    failed = 0
    errored = 0
    total_input = 0
    total_placed = 0
    total_unplaced = 0
    for row in cases:
        if not isinstance(row, dict):
            row_errors.append("manifest cases の要素が不正です")
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name:
            row_errors.append("case.name は空でない文字列で指定してください")
            continue
        if name in seen_names:
            row_errors.append(f"case.name が重複しています: {name}")
            continue
        seen_names.add(name)

        status = row.get("status")
        if status not in _KNOWN_STATUS:
            row_errors.append(f"status が不正です ({name}): {status}")
            continue

        elapsed = row.get("elapsed_seconds")
        if not (
            isinstance(elapsed, (int, float))
            and not isinstance(elapsed, bool)
            and elapsed >= 0
        ):
            row_errors.append(f"elapsed_seconds が不正です ({name})")
            continue

        if status == "ERROR":
            errored += 1
            error_detail = row.get("error")
            if not isinstance(error_detail, str) or not error_detail:
                row_errors.append(f"ERROR ケースの error が不正です ({name})")
                continue
            for forbidden in ("result_file", "input", "placed", "unplaced", "violations"):
                if forbidden in row:
                    row_errors.append(f"ERROR ケースに {forbidden} を含めることはできません ({name})")
            entries.append({"filename": None, "case": row, "data": None})
            continue

        if status == "PASS":
            passed += 1
        else:
            failed += 1

        for key in ("input", "placed", "unplaced"):
            if not _is_non_negative_int(row.get(key)):
                row_errors.append(f"{key} が不正です ({name})")
                break
        else:
            if row["input"] != row["placed"] + row["unplaced"]:
                row_errors.append(f"input と placed/unplaced の整合が不正です ({name})")
                continue
        if not isinstance(row.get("violations"), list) or not all(isinstance(x, str) for x in row["violations"]):
            row_errors.append(f"violations が不正です ({name})")
            continue

        filename = row.get("result_file")
        expected_filename = f"result_{name}.json"
        if not isinstance(filename, str):
            row_errors.append(f"result_file が不正です: {name}")
            continue
        if filename != expected_filename:
            row_errors.append(f"result_file が case 名と一致しません ({name}): {filename}")
            continue
        if Path(filename).name != filename or not filename.startswith("result_") or not filename.endswith(".json"):
            row_errors.append(f"result_file 名が不正です: {filename}")
            continue
        if filename in seen_files:
            row_errors.append(f"result_file が重複しています: {filename}")
            continue
        seen_files.add(filename)

        total_input += row["input"]
        total_placed += row["placed"]
        total_unplaced += row["unplaced"]

        result_path = results_dir / filename
        if not result_path.is_file():
            row_errors.append(f"結果JSONが見つかりません: {filename}")
            continue
        try:
            data = _read_json(result_path)
            validate_part_result_payload(data, source=filename)
        except ValueError as error:
            row_errors.append(str(error))
            continue

        if data.get("test_name") != name:
            row_errors.append(f"{filename}: test_name が manifest 名と一致しません ({name})")
            continue
        if data.get("catalog_revision") != revision:
            row_errors.append(f"{filename}: catalog_revision が manifest と一致しません")
            continue
        if data.get("input_boxes_count") != row["input"]:
            row_errors.append(f"{filename}: input_boxes_count が manifest と一致しません")
            continue
        if data.get("placed_boxes_count") != row["placed"]:
            row_errors.append(f"{filename}: placed_boxes_count が manifest と一致しません")
            continue
        if data.get("unplaced_boxes_count") != row["unplaced"]:
            row_errors.append(f"{filename}: unplaced_boxes_count が manifest と一致しません")
            continue

        summary = data.get("summary")
        if not isinstance(summary, dict):
            row_errors.append(f"{filename}: summary が不正です")
            continue
        is_valid = summary.get("is_valid")
        if not isinstance(is_valid, bool):
            row_errors.append(f"{filename}: summary.is_valid が不正です")
            continue
        expected_status = "PASS" if is_valid else "FAIL"
        if status != expected_status:
            row_errors.append(
                f"{filename}: status が summary.is_valid と一致しません ({status} != {expected_status})"
            )
            continue
        violations = summary.get("violations")
        if not isinstance(violations, list) or not all(isinstance(x, str) for x in violations):
            row_errors.append(f"{filename}: summary.violations が不正です")
            continue
        if violations != row["violations"]:
            row_errors.append(f"{filename}: violations が manifest と一致しません")
            continue

        entries.append({"filename": filename, "case": row, "data": data})

    summary_errors = []
    expected_counts = {
        "cases": len(cases),
        "passed": passed,
        "failed": failed,
        "errors": errored,
        "input": total_input,
        "placed": total_placed,
        "unplaced": total_unplaced,
    }
    for key, expected in expected_counts.items():
        actual = counts.get(key)
        if actual != expected:
            summary_errors.append(f"counts.{key} が実測と一致しません ({actual} != {expected})")

    if row_errors or summary_errors:
        details = row_errors + summary_errors
        raise ValueError("結果フォルダに表示不可データがあります:\n- " + "\n- ".join(details))
    if not entries:
        raise ValueError("実行一覧にケースがありません")
    return entries


def resolve_latest_completed_catalog_run(catalog_results_root: Path) -> Path:
    if not catalog_results_root.is_dir():
        raise ValueError(f"catalog_results フォルダがありません: {catalog_results_root}")

    run_dirs = sorted(
        (path for path in catalog_results_root.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not run_dirs and not (catalog_results_root / RUN_MANIFEST_NAME).is_file():
        raise ValueError(
            f"{catalog_results_root} に実行フォルダがありません。"
            "先に catalog runner で結果を作成してください"
        )

    latest_completed = None
    for path in run_dirs:
        if (path / RUN_MANIFEST_NAME).is_file():
            latest_completed = path
            break
    if latest_completed is None and (catalog_results_root / RUN_MANIFEST_NAME).is_file():
        latest_completed = catalog_results_root
    if latest_completed is None:
        raise ValueError(
            f"{catalog_results_root} に run_manifest.json を含む完了実行フォルダがありません。"
            "実行中フォルダは無視されます。完了後に再実行してください"
        )
    try:
        load_part_results_from_manifest(latest_completed)
    except ValueError as error:
        raise ValueError(
            f"最新完了実行フォルダ {latest_completed.name} が不正です: {error}\n"
            "古い結果へはフォールバックしません。最新runを修正または再実行してください"
        ) from error
    return latest_completed
