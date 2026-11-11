"""品番DB移行の事前確認。入力は変更せず、確認用ファイルだけを生成する。"""

import argparse
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from box_research.database_validation import normalize_id, validate_box_lid_databases
from constraints.top_support import required_support_points


MODEL_NAMES = {
    "NP22C": "サンボックス#22H", "NPP24": "サンボックス#22H",
    "SPZ36404": "TP364", "SPZ36406": "TP364",
}
SUPPLIER_NAMES = {"クゼー": "グゼー", "NITTAN": "ニッタン"}
LID_LABELS = {
    **{"TP" + size: "TP" + size + "フタ" for size in ("330", "340", "360", "460")},
    **{"サンボックス" + size: "サンボックス" + size + "フタ"
       for size in ("330", "340", "360", "460")},
    "サンボックス#22B": "サンボックス#22Bフタ",
}
LID_OVERRIDES = {
    "130902501000": ("TP341", "TP34蓋"),
    "153702502000": ("TP341", "TP340フタ"),
    "155202501000": ("TP331", "無蓋"),
}
ADDITIONAL_MODELS = {
    "NEUAD9": {
        "id": "NEUAD9", "type": "NON_TP", "length": 540, "width": 365,
        "height": 70, "fitting_depth": 5, "rib_thickness": 15,
        "module_ratio": None, "compatible_lids": [], "top_support_points": 4,
    },
    "NS80858": {
        "id": "NS80858", "type": "NON_TP", "length": 1400, "width": 1000,
        "height": 800, "fitting_depth": 10, "rib_thickness": 15,
        "module_ratio": None, "compatible_lids": [], "top_support_points": 4,
    },
}
SPEC_FIELDS = (
    "type", "length", "width", "height", "fitting_depth",
    "rib_thickness", "module_ratio", "top_support_points",
)


def supplier_name(value: str) -> str:
    normalized = normalize_id(value)
    return SUPPLIER_NAMES.get(normalized, normalized)


def lid_name(value: str) -> str:
    normalized = normalize_id(value)
    return LID_LABELS.get(normalized, normalized)


def _read_json(path: Path) -> Any:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("{}: JSONキーが重複しています: {}".format(path, key))
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys)


def build_preview(root: Path) -> Dict[str, Any]:
    """現在のCSV・DB・全ケースから未適用の移行案を作る。"""
    db_dir = root / "box_research"
    csv_path = db_dir / "box_list.csv"
    box_path, lid_path = db_dir / "box_db.json", db_dir / "lid_db.json"
    case_paths = sorted((root / "test_programmer" / "test_cases").glob("*.json"))
    if not case_paths:
        raise ValueError("確認対象のテストケースがありません")
    inputs = [csv_path, box_path, lid_path] + case_paths
    hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in inputs}
    boxes, lids = _read_json(box_path), _read_json(lid_path)
    validate_box_lid_databases(boxes, lids)
    issues: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []

    def issue(severity: str, kind: str, source: str, detail: str) -> None:
        issues.append(dict(severity=severity, kind=kind, source=source, detail=detail))

    def change(kind: str, source: str, before: str, after: str) -> None:
        if before != after:
            changes.append(dict(kind=kind, source=source, before=before, after=after))

    def index_records(records, transform, kind):
        indexed = {}
        for old_id, record in records.items():
            new_id = transform(old_id)
            if not new_id:
                raise ValueError("{}: 変換後のIDが空です".format(old_id))
            change(kind, old_id, old_id, new_id)
            if new_id in indexed:
                issue("blocker", "id_collision", old_id, "変換後IDが重複: " + new_id)
                continue
            indexed[new_id] = copy.deepcopy(record)
            indexed[new_id]["id"] = new_id
        return indexed

    normalized_lids = index_records(lids, lid_name, "lid_id")
    normalized_boxes = index_records(boxes, normalize_id, "box_name")
    models: Dict[str, Any] = {}
    model_sources: Dict[str, List[str]] = {}
    model_mapping = {}
    for box_id, record in normalized_boxes.items():
        model_id = MODEL_NAMES.get(box_id, box_id)
        model_mapping[box_id] = model_id
        change("model_mapping", box_id, box_id, model_id)
        proposed = copy.deepcopy(record)
        proposed.pop("name", None)
        proposed["id"] = model_id
        proposed["compatible_lids"] = [lid_name(lid) for lid in record.get("compatible_lids", [])]
        proposed["top_support_points"] = required_support_points(box_id, record)
        if model_id in models:
            existing = models[model_id]
            if (box_id not in MODEL_NAMES
                    or any(source not in MODEL_NAMES for source in model_sources[model_id])
                    or any(
                    existing.get(field) != proposed.get(field) for field in SPEC_FIELDS)):
                issue("blocker", "model_collision", box_id,
                      "共通モデル名が衝突、または仕様が不一致: " + model_id)
            existing["compatible_lids"] = sorted(set(
                existing["compatible_lids"] + proposed["compatible_lids"]))
        else:
            models[model_id] = proposed
            model_sources[model_id] = []
        model_sources[model_id].append(box_id)
    for model_id, record in ADDITIONAL_MODELS.items():
        if model_id in models:
            if any(models[model_id].get(field) != record.get(field) for field in SPEC_FIELDS):
                issue("blocker", "additional_model_conflict", model_id, "追加指定と現DBの仕様が不一致")
        else:
            models[model_id] = copy.deepcopy(record)
            change("new_model", model_id, "", model_id)

    no_lids = [key for key, record in normalized_lids.items() if record.get("type") == "NONE"]
    if no_lids != ["無蓋"]:
        raise ValueError("無蓋の登録が想定と異なります。確認が必要です: {}".format(no_lids))
    for model_id, record in models.items():
        for lid_id in record["compatible_lids"]:
            if lid_id not in normalized_lids:
                issue("blocker", "unknown_compatible_lid", model_id, lid_id)

    parts: Dict[str, Any] = {}
    duplicate_count = 0
    blank_count = 0
    raw_count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["仕入先名", "品番", "箱種", "型式"]:
            raise ValueError("CSVの列は 仕入先名,品番,箱種,型式 の順で指定してください")
        for row in reader:
            raw_count += 1
            location = "box_list.csv:{}".format(reader.line_num)
            if None in row or any(value is None for value in row.values()):
                raise ValueError(location + ": CSVの列数が不正です")
            values = {key: normalize_id(value) for key, value in row.items()}
            if not any(values.values()):
                blank_count += 1
                continue
            if not all(values[key] for key in ("仕入先名", "品番", "箱種")):
                raise ValueError(location + ": 仕入先名・品番・箱種は必須です")
            part_id, box_id = values["品番"], values["箱種"]
            selected_lid = lid_name(values["型式"]) if values["型式"] else "無蓋"
            for key, value in values.items():
                change("csv_normalization", location + ":" + key, row[key], value)
            original_lid = selected_lid
            if part_id in LID_OVERRIDES:
                expected_box, selected_lid = LID_OVERRIDES[part_id]
                if box_id != expected_box:
                    issue("blocker", "override_box_mismatch", location,
                          "蓋の補正指示と箱名称が一致しません: " + part_id)
            change("lid_resolution", location, row["型式"], selected_lid)
            if original_lid != selected_lid:
                change("approved_lid_override", part_id, original_lid, selected_lid)
            supplier = supplier_name(row["仕入先名"])
            change("supplier_alias", location, values["仕入先名"], supplier)
            model_id = model_mapping.get(box_id, box_id)
            proposed = dict(
                id=part_id, supplier_name=supplier, box_name=box_id,
                box_model_id=model_id, lid_id=selected_lid,
            )
            if part_id in parts:
                if any(parts[part_id][key] != value for key, value in proposed.items()):
                    issue("blocker", "part_collision", location,
                          "同じ品番で仕入先・箱・蓋が異なります: " + part_id)
                elif any(parts[part_id]["source_row"][key] != row[key] for key in row):
                    issue("blocker", "normalized_part_collision", location,
                          "表記変換後に品番が重複しました。自動統合しません: " + part_id)
                else:
                    duplicate_count += 1
                    parts[part_id]["source_lines"].append(reader.line_num)
                    issue("info", "exact_duplicate", location, "同一内容を統合: " + part_id)
                continue
            valid = True
            if model_id not in models:
                valid = False
                issue("blocker", "unknown_model", location, model_id)
            if selected_lid not in normalized_lids:
                valid = False
                issue("blocker", "unknown_lid", location, selected_lid)
            elif (model_id in models and normalized_lids[selected_lid].get("type") != "NONE"
                  and selected_lid not in models[model_id]["compatible_lids"]):
                valid = False
                issue("blocker", "incompatible_lid", location, part_id + ": " + selected_lid)
            proposed.update(source_lines=[reader.line_num], source_row=dict(row), valid=valid)
            parts[part_id] = proposed

    case_rows = []
    for path in case_paths:
        case = _read_json(path)
        supplier = supplier_name(case["supplier_name"])
        change("case_supplier", path.name, case["supplier_name"], supplier)
        for index, row in enumerate(case["box_list"], 1):
            source = "{}:箱行{}".format(path.name, index)
            box_id = normalize_id(row["box_id"])
            selected_lid = lid_name(row.get("lid_id", "無蓋"))
            candidates = [
                part for part in parts.values()
                if part["valid"] and part["supplier_name"] == supplier
                and part["box_name"] == box_id and part["lid_id"] == selected_lid
            ]
            selected = candidates[0]["id"] if candidates else ""
            status = "unique" if len(candidates) == 1 else "first_candidate"
            if not candidates:
                status = "unmatched"
                issue("blocker", "unmatched_case", source,
                      "仕入先・箱名称・蓋が一致する品番なし: {}/{}/{}".format(
                          supplier, box_id, selected_lid))
            elif len(candidates) > 1:
                issue("review", "first_candidate", source,
                      "CSV順の第一候補 {} を仮選択（{}候補）".format(selected, len(candidates)))
            case_rows.append(dict(
                case_file=path.name, row=index, supplier_name=supplier,
                old_box_id=row["box_id"], box_name=box_id,
                old_lid_id=row.get("lid_id", "無蓋"), lid_id=selected_lid,
                count=row["count"], part_number=selected, status=status,
                candidates=[part["id"] for part in candidates],
            ))
    counts = {
        "csv_rows": raw_count, "blank_rows": blank_count, "exact_duplicates": duplicate_count,
        "parts": len(parts), "models": len(models), "lids": len(normalized_lids),
        "cases": len(case_paths), "case_rows": len(case_rows),
        "unique_case_rows": sum(row["status"] == "unique" for row in case_rows),
        "first_candidate_rows": sum(row["status"] == "first_candidate" for row in case_rows),
        "unmatched_case_rows": sum(row["status"] == "unmatched" for row in case_rows),
        "blockers": sum(item["severity"] == "blocker" for item in issues),
    }
    return dict(
        stage="preview_only", applied=False, requires_user_approval=True,
        source_sha256=hashes, counts=counts, parts=list(parts.values()),
        models=models, lids=normalized_lids, model_mapping=model_mapping,
        case_rows=case_rows, changes=changes, issues=issues,
    )


def write_preview(report: Dict[str, Any], output_dir: Path, root: Path) -> None:
    """新しい出力専用フォルダへ確認資料を保存する。既存ファイルは上書きしない。"""
    output_dir, root = output_dir.resolve(), root.resolve()
    if output_dir == root or output_dir in root.parents:
        raise ValueError("出力先は確認資料専用の新しいフォルダにしてください")
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "preview.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tables = {
        "parts": (report["parts"], [
            "id", "supplier_name", "box_name", "box_model_id", "lid_id", "valid", "source_lines"]),
        "cases": (report["case_rows"], [
            "case_file", "row", "supplier_name", "old_box_id", "box_name",
            "old_lid_id", "lid_id", "count", "part_number", "status", "candidates"]),
        "changes": (report["changes"], ["kind", "source", "before", "after"]),
        "issues": (report["issues"], ["severity", "kind", "source", "detail"]),
    }
    for name, (rows, fields) in tables.items():
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False)
                             if isinstance(value, list) else value for key, value in row.items()})
        (output_dir / (name + ".csv")).write_text(buffer.getvalue(), encoding="utf-8-sig")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="まだ存在しない確認資料専用フォルダ")
    args = parser.parse_args()
    try:
        report = build_preview(ROOT)
        for relative, digest in report["source_sha256"].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
                raise ValueError("調査中に入力が変更されました。再実行してください: " + relative)
        write_preview(report, args.output_dir, ROOT)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        parser.exit(1, "事前確認に失敗しました: {}\n".format(error))
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    print("確認資料: {}".format(args.output_dir.resolve()))
    print("DB・ケースへの適用はしていません。第2段階にはユーザーの確認が必要です。")
    return 2 if report["counts"]["blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
