"""品番結果をDB・ケースと照合する独立検証。計算エンジンには依存しない。"""

import copy
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from box_research.catalog_store import catalog_pallets, load_catalog


IDENTITY_FIELDS = ("part_number", "supplier_name", "box_name", "box_id", "box_model_id", "lid_id")


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(label + ": 不正な整数です")
    return value


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ": 有限の数値が必要です")
    return value


def resolve_catalog_result(
    data: Dict[str, Any], catalog: Optional[Dict[str, Any]], revision: Optional[str],
    pallets: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """数量・品番・固定蓋等を検証後、幾何判定用のモデルIDに解決する。"""
    if catalog is None or revision is None or pallets is None:
        raise ValueError("品番DBを読み込んで検証してください（--results-dir）")
    if (data.get("schema_version") != 2 or data.get("input_mode") != "part_number"
            or data.get("coordinate_reference") != "combined_footprint_min_xy_top_z"):
        raise ValueError("品番結果の形式・座標基準が不正です")
    if data.get("catalog_revision") != revision:
        raise ValueError("結果と現在のDB・ケースの照合値が異なります。再計算してください")
    name = data.get("test_name")
    cases = catalog.get("cases", {}).get("test_cases", {})
    if not isinstance(name, str) or name not in cases:
        raise ValueError("結果のケース名が保存済み品番ケースにありません")
    case = cases[name]
    if data.get("supplier_name") != case["supplier_name"] or data.get("pallet_id") != case["pallet_id"]:
        raise ValueError("結果の仕入先・パレットIDがケースと一致しません")
    pallet = pallets["pallets"][case["pallet_id"]]
    expected_pallet = {key: pallet[key] for key in ("length", "width", "height")}
    expected_pallet.update(case["pallet"])
    if not isinstance(data.get("pallet"), dict):
        raise ValueError("結果のパレット設定がありません")
    for key, expected in expected_pallet.items():
        if _number(data["pallet"].get(key), "pallet." + key) != expected:
            raise ValueError("結果のパレット設定がDB・ケースと異なります: " + key)

    expected_counts: Dict[str, int] = {}
    for row in case["box_list"]:
        key = row["part_number"]
        expected_counts[key] = expected_counts.get(key, 0) + row["count"]
    parts = catalog["parts"]
    identities = {
        key: dict(part_number=key, box_id=parts[key]["box_name"],
                  **{field: parts[key][field] for field in
                     ("supplier_name", "box_name", "box_model_id", "lid_id")})
        for key in expected_counts
    }

    def identity(row: Any) -> str:
        if not isinstance(row, dict):
            raise ValueError("箱・品番行はオブジェクトが必要です")
        key = row.get("part_number")
        if not isinstance(key, str) or key not in identities:
            raise ValueError("投入していない品番が結果にあります")
        if any(row.get(field) != identities[key][field] for field in IDENTITY_FIELDS):
            raise ValueError(key + ": 箱名称・共通モデル・仕入先・固定蓋がDBと一致しません")
        return key

    boxes = data.get("boxes")
    if not isinstance(boxes, list):
        raise ValueError("配置箱一覧がありません")
    placed: Counter = Counter()
    orders = []
    model_groups: Dict[Tuple[str, str], List[str]] = {}
    for key in expected_counts:
        part = parts[key]
        model_groups.setdefault((part["box_model_id"], part["lid_id"]), []).append(key)
    allocation_counts: Counter = Counter()
    for box in boxes:
        key = identity(box)
        order = _integer(box.get("order"), key + ".order", 1)
        orders.append(order)
        placed[key] += 1
        if box.get("rotation") not in (0, 90) or type(box.get("rotation")) is not int:
            raise ValueError(key + ": 回転角は整数0または90です")
        for field in ("position", "dimensions", "lid_dimensions"):
            record = box.get(field)
            if not isinstance(record, dict):
                raise ValueError(key + ": " + field + "がありません")
            for axis in (("x", "y", "z") if field == "position" else
                         ("width", "length", "height") if field == "dimensions" else ("width", "length")):
                value = _number(record.get(axis), key + "." + field + "." + axis)
                if field != "position" and (value < 0 or (field == "dimensions" and value == 0)):
                    raise ValueError(key + ": 箱・蓋寸法が不正です")
        model = catalog["models"][box["box_model_id"]]
        for field in ("fitting_depth",) + (("rib_thickness",) if "rib_thickness" in box else ()):
            if abs(_number(box.get(field), key + "." + field) - model[field]) > 1e-3:
                raise ValueError(key + ": " + field + "がモデルDBと一致しません")
        _number(box.get("lid_thickness"), key + ".lid_thickness")
        _integer(box.get("layer_index"), key + ".layer_index")
        supports = box.get("supported_by")
        if (not isinstance(supports, list) or any(type(s) is not int or not 1 <= s < order for s in supports)
                or len(supports) != len(set(supports))):
            raise ValueError(key + ": 下段支持番号が不正です")
        candidates = model_groups[(box["box_model_id"], box["lid_id"])]
        expected_part = next((p for p in candidates if allocation_counts[p] < expected_counts[p]), None)
        if key != expected_part:
            raise ValueError("入力順の品番配分または投入数量が一致しません")
        allocation_counts[key] += 1
    if orders != list(range(1, len(boxes) + 1)):
        raise ValueError("積み順は1から連続した整数順である必要があります")

    missing: Counter = Counter()
    unplaced = data.get("unplaced_boxes")
    if not isinstance(unplaced, list):
        raise ValueError("未配置箱一覧がありません")
    for row in unplaced:
        key = identity(row)
        if missing[key]:
            raise ValueError(key + ": 未配置行が重複しています")
        missing[key] = _integer(row.get("count"), key + ".unplaced", 1)
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError(key + ": 未配置理由がありません")
    if placed + missing != Counter(expected_counts):
        raise ValueError("品番別の投入数＝配置数＋未配置数が一致しません")
    for field, expected in (("input_boxes_count", sum(expected_counts.values())),
                            ("placed_boxes_count", len(boxes)),
                            ("unplaced_boxes_count", sum(missing.values()))):
        if _integer(data.get(field), field) != expected:
            raise ValueError(field + "が実際の数量と一致しません")
    expected_parts = [dict(identities[key], count=count) for key, count in expected_counts.items()]
    expected_rows = [dict(identities[key], input_count=count, placed_count=placed[key],
                          unplaced_count=missing[key]) for key, count in expected_counts.items()]
    for field, counts in (("input_parts", ("count",)),
                           ("part_counts", ("input_count", "placed_count", "unplaced_count"))):
        rows = data.get(field)
        if not isinstance(rows, list):
            raise ValueError(field + "がありません")
        for row in rows:
            identity(row)
            for count in counts:
                _integer(row.get(count), field + "." + count)
    if data.get("input_parts") != expected_parts or data.get("part_counts") != expected_rows:
        raise ValueError("投入品番一覧・品番別集計がケースと配置箱に一致しません")
    variants = [{field: row[field] for field in
                 ("part_number", "box_id", "box_name", "box_model_id", "lid_id")} for row in expected_parts]
    if data.get("input_box_variants") != variants:
        raise ValueError("投入箱種類が品番ケースと一致しません")
    if (data.get("allocation_method") != "input_order" or
            data.get("algorithm_mode") != ("single" if len(model_groups) == 1 else "mixed")):
        raise ValueError("計算方式または品番配分方式が一致しません")
    resolved = copy.deepcopy(data)
    for box in resolved["boxes"]:
        box["box_id"] = parts[box["part_number"]]["box_model_id"]
        if box["position"]["z"] - box["dimensions"]["height"] < -1e-3:
            raise ValueError("箱の底面がパレット上面より下にあります")
    return resolved, expected_rows


def validate_catalog_run(root: Path, results_dir: Path, report_dir: Path) -> int:
    """今回の一括実行一覧を照合し、採用済み全件の独立レポートを別保存する。"""
    from supervisor.validate import PalletizeValidator

    results_dir = results_dir.resolve()
    if not results_dir.exists() or not results_dir.is_dir():
        raise ValueError("結果フォルダが存在しません: " + str(results_dir))
    catalog, revision = load_catalog(root)
    pallets = catalog_pallets(root, catalog["pallets"])
    manifest = json.loads((results_dir / "run_manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("input_mode") != "part_number"
            or manifest.get("source") != "catalog_store"
            or manifest.get("catalog_revision") != revision):
        raise ValueError("実行一覧と現在の品番DBの照合値が一致しません。再計算してください")
    approved = {name for name, state in catalog["cases"]["approval_state"].items() if state}
    rows = manifest.get("cases")
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or len(rows) != len(approved) or {row.get("name") for row in rows} != approved):
        raise ValueError("実行一覧が現在の採用済みケース全件と一致しません")
    runner_counts = dict(cases=0, passed=0, failed=0, errors=0, input=0, placed=0, unplaced=0)
    for row in rows:
        name = row["name"]
        status = row.get("status")
        if status not in ("PASS", "FAIL", "ERROR"):
            raise ValueError(name + ": 実行一覧の判定が不正です")
        runner_counts["cases"] += 1
        if status == "PASS":
            runner_counts["passed"] += 1
        elif status == "FAIL":
            runner_counts["failed"] += 1
        else:
            runner_counts["errors"] += 1
            if not isinstance(row.get("error"), str) or not row["error"].strip():
                raise ValueError(name + ": ERROR行の内容が不正です")
            continue
        filename = "result_" + name + ".json"
        if row.get("result_file") != filename:
            raise ValueError(name + ": 実行一覧の結果ファイル名が不正です")
        for key in ("input", "placed", "unplaced"):
            runner_counts[key] += _integer(row.get(key), name + "." + key)
    manifest_counts = manifest.get("counts")
    if not isinstance(manifest_counts, dict):
        raise ValueError("実行一覧の件数集計が不正です")
    if set(manifest_counts) != set(runner_counts):
        raise ValueError("実行一覧の件数集計キーが不正です")
    for key, expected in runner_counts.items():
        actual = _integer(manifest_counts.get(key), "counts." + key)
        if actual != expected:
            raise ValueError("実行一覧の件数集計が実行一覧行と一致しません: " + key)

    validator = PalletizeValidator(catalog["models"], catalog["lids"], catalog, revision, pallets)
    reports = []
    independent_statuses: Dict[str, str] = {}
    independent_counts = dict(cases=0, passed=0, failed=0, errors=0, input=0, placed=0, unplaced=0)
    for row in rows:
        name = row["name"]
        status = row["status"]
        independent_counts["cases"] += 1
        if row.get("status") == "ERROR":
            report = validator._empty_report(name, ["計算時エラー: " + str(row.get("error"))], [])
            independent_status = "ERROR"
        elif status in ("PASS", "FAIL"):
            filename = row["result_file"]
            try:
                data = json.loads((results_dir / filename).read_text(encoding="utf-8"))
                if not isinstance(data, dict) or data.get("test_name") != name:
                    raise ValueError("結果のケース名が実行一覧と一致しません")
                report = validator.validate_data(data)
                independent_status = "PASS" if report["is_pass"] else "FAIL"
            except (OSError, ValueError, TypeError, KeyError) as error:
                report = validator._empty_report(name, ["結果読込エラー: " + str(error)], [])
                independent_status = "ERROR"
        else:
            raise ValueError(name + ": 実行一覧の判定が不正です")
        independent_statuses[name] = independent_status
        if independent_status == "PASS":
            independent_counts["passed"] += 1
        elif independent_status == "FAIL":
            independent_counts["failed"] += 1
        else:
            independent_counts["errors"] += 1
        if independent_status != "ERROR":
            independent_counts["input"] += report.get("input_boxes_count") or 0
            independent_counts["placed"] += report["total_boxes"]
            independent_counts["unplaced"] += report.get("unplaced_boxes_count") or 0
        reports.append(report)
        print("{} [{}]".format(independent_status, name))

    report_dir = report_dir.resolve()
    if report_dir == (root / "supervisor" / "reports").resolve():
        raise ValueError("旧方式のレポートフォルダを上書きできません")
    report_dir.mkdir(parents=True, exist_ok=False)
    for report in reports:
        (report_dir / ("report_" + report["test_name"] + ".json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    summary = dict(
        catalog_revision=revision,
        source="catalog_store",
        counts=independent_counts,
        independent_counts=independent_counts,
        runner_counts=runner_counts,
    )
    (report_dir / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    def cell(value: Any) -> str:
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(
            "|", "&#124;").replace("\n", " ").replace("\r", " ")

    lines = ["# 品番方式・独立検証レポート", "",
             "判定は結果内のsummaryではなく、現在のDB・ケースと配置座標から再計算しています。",
             "照合値: `" + revision + "`", "",
             "独立判定 件数: {cases} / PASS: {passed} / FAIL: {failed} / エラー: {errors}".format(
                 **independent_counts),
             "独立判定 投入: {input} / 配置: {placed} / 未配置: {unplaced}".format(**independent_counts),
             "実行一覧 件数: {cases} / PASS: {passed} / FAIL: {failed} / ERROR: {errors}".format(
                 **runner_counts),
             "実行一覧 投入: {input} / 配置: {placed} / 未配置: {unplaced}".format(**runner_counts),
             "未配置が0かどうかは制約合否とは別に確認してください。", "",
             "| ケース | 判定 | 投入 | 配置 | 未配置 | 違反 |", "|---|---|---:|---:|---:|---|"]
    for report in reports:
        messages = cell(" / ".join(report["violations"]))
        status = independent_statuses.get(report["test_name"], "FAIL")
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            report["test_name"], status,
            report.get("input_boxes_count", "—"), report["total_boxes"],
            report.get("unplaced_boxes_count", "—"), messages))
    lines.extend(["", "## 品番別数量", "",
                  "| ケース | 品番 | 仕入先 | 箱名称 | 共通モデル | 固定蓋 | 投入 | 配置 | 未配置 |",
                  "|---|---|---|---|---|---|---:|---:|---:|"])
    for report in reports:
        for row in report.get("part_counts", []):
            values = [report["test_name"]] + [row[key] for key in IDENTITY_FIELDS if key != "box_id"]
            values.extend(row[key] for key in ("input_count", "placed_count", "unplaced_count"))
            lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.extend(["", "## 要確認事項（合否とは別）", ""])
    for report in reports:
        for warning in report["warnings"]:
            lines.append("- {}: {}".format(report["test_name"], cell(warning)))
    (report_dir / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(independent_counts, ensure_ascii=False))
    return 1 if independent_counts["failed"] or independent_counts["errors"] else 0
