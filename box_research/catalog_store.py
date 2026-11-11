"""品番・モデルDBとケース保存。旧方式のデータとは分離する。"""

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import re
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from box_research.database_validation import (
    normalize_id, validate_catalog_databases, validate_part_case_references,
    validate_case_pallet_reference, validate_pallet_database,
)
from box_research.preview_migration import _read_json, build_preview, supplier_name

FILES = {
    "parts": "box_type_db.json", "models": "box_model_db.json",
    "lids": "lid_db.json", "migration": "migration.json",
}


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _paths(root: Path) -> Dict[str, Path]:
    directory = root / "box_research" / "catalog"
    return {**{key: directory / filename for key, filename in FILES.items()},
            "cases": directory / "test_cases.json"}


def _revision(root: Path) -> str:
    hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
              for key, path in _paths(root).items()}
    return hashlib.sha256(_encoded(hashes)).hexdigest()


def normalize_catalog(data: Dict[str, Any]) -> Dict[str, Any]:
    """入力文字を正規化する。同じIDへの衝突は上書きせず拒否する。"""
    if not isinstance(data, dict) or set(data) not in (set(FILES), set(FILES) | {"cases"}):
        raise ValueError("品番・箱モデル・蓋・移行情報の4種類が必要です")
    result = copy.deepcopy(data)
    for collection in ("parts", "models", "lids"):
        if not isinstance(result[collection], dict):
            raise ValueError(collection + "はオブジェクトが必要です")
        records = {}
        for key, record in result[collection].items():
            if not isinstance(record, dict) or record.get("id") != key:
                raise ValueError(collection + ": キーとIDが一致しません")
            normalized = normalize_id(key)
            if normalized in records:
                raise ValueError("正規化後のIDが重複しています: " + normalized)
            record["id"] = normalized
            records[normalized] = record
        result[collection] = records
    for part in result["parts"].values():
        for field in ("supplier_name", "box_name", "box_model_id", "lid_id"):
            part[field] = (supplier_name(part.get(field)) if field == "supplier_name"
                           else normalize_id(part.get(field)))
    for model in result["models"].values():
        compatible = model.get("compatible_lids")
        if not isinstance(compatible, list):
            raise ValueError("互換蓋は配列が必要です")
        model["compatible_lids"] = [normalize_id(value) for value in compatible]
    if "cases" in result:
        for case in result["cases"]["test_cases"].values():
            case["supplier_name"] = supplier_name(case.get("supplier_name"))
            for row in case["box_list"]:
                row["part_number"] = normalize_id(row.get("part_number"))
    return result


def validate_catalog(data: Dict[str, Any]) -> None:
    """DB間の参照に加えて、移行予定のケース・旧名称の参照も保護する。"""
    if set(data) not in (set(FILES), set(FILES) | {"cases"}):
        raise ValueError("カタログの構成が不正です")
    validate_catalog_databases(data["parts"], data["models"], data["lids"])
    migration = data["migration"]
    if (not isinstance(migration, dict) or migration.get("schema_version") != 1
            or migration.get("phase") not in (
                "phase2_pending_activation", "phase3_pending_algorithm",
                "phase4_pending_validation", "phase5_ready")):
        raise ValueError("移行情報の版または段階が不正です")
    for mapping_name in ("legacy_model_mapping", "model_name_history"):
        mapping = migration.get(mapping_name)
        if not isinstance(mapping, dict):
            raise ValueError(mapping_name + "がありません")
        for old, current in mapping.items():
            if (not isinstance(old, str) or not old or not isinstance(current, str)
                    or current not in data["models"]):
                raise ValueError(mapping_name + ": 旧名称の参照先が不正です")
            if mapping_name == "model_name_history" and old in data["models"]:
                raise ValueError("旧名称を別モデルへ再利用できません: " + old)
    assignments = migration.get("case_assignments")
    if not isinstance(assignments, list):
        raise ValueError("ケース対応表がありません")
    seen = set()
    for assignment in assignments:
        key = (assignment["case_file"], assignment["row"])
        if key in seen:
            raise ValueError("ケース対応行が重複しています: " + str(key))
        seen.add(key)
        if "cases" not in data:
            part_id = assignment["part_number"]
            validate_part_case_references({
                "supplier_name": assignment["supplier_name"],
                "box_list": [{"part_number": part_id, "count": assignment["count"],
                              "lid_id": assignment["lid_id"]}],
            }, data["parts"])
            if data["parts"][part_id]["box_name"] != assignment["box_name"]:
                raise ValueError("ケース対応と品番の箱名称が一致しません: " + part_id)
    if "cases" in data:
        validate_staged_cases(data["cases"], data["parts"])


def validate_staged_cases(bundle: Dict[str, Any], parts: Dict[str, Any],
                          pallets: Optional[Dict[str, Any]] = None) -> None:
    """切替準備用ケースと採用状態を検証する。計算用ケースには保存しない。"""
    if (not isinstance(bundle, dict) or set(bundle) != {"schema_version", "test_cases", "approval_state"}
            or bundle["schema_version"] != 1
            or not isinstance(bundle["test_cases"], dict)
            or not isinstance(bundle["approval_state"], dict)
            or set(bundle["test_cases"]) != set(bundle["approval_state"])):
        raise ValueError("準備用ケースと採用状態の構成が不正です")
    for case_id, case in bundle["test_cases"].items():
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", case_id):
            raise ValueError("ケースIDは英数字・ハイフン・下線で指定してください")
        if (not isinstance(case, dict) or case.get("name") != case_id
                or not isinstance(case.get("description"), str) or not case["description"].strip()
                or type(bundle["approval_state"][case_id]) is not bool):
            raise ValueError(case_id + ": 名前・説明・採用状態が不正です")
        validate_part_case_references(case, parts)
        if any(set(row) != {"part_number", "count"} for row in case["box_list"]):
            raise ValueError(case_id + ": 箱行には品番と数量だけを保存してください")
        pallet = case.get("pallet")
        if not isinstance(pallet, dict) or set(pallet) != {"max_x_span", "max_y_span", "max_height"}:
            raise ValueError(case_id + ": 荷山上限の3項目が必要です")
        for value in pallet.values():
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                raise ValueError(case_id + ": 荷山上限は0より大きい有限数値です")
        if pallet["max_x_span"] < pallet["max_y_span"]:
            raise ValueError(case_id + ": 最大Lは最大W以上にしてください")
        if pallets is not None:
            validate_case_pallet_reference(case_id, case, pallets)


def catalog_pallets(root: Path, pallet_database: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """既存パレットDBは変更せず、仕入先名だけ新方式と揃えて参照する。"""
    pallets = validate_pallet_database(
        _read_json(root / "box_research" / "pallet_db.json") if pallet_database is None
        else copy.deepcopy(pallet_database))
    for pallet in pallets["pallets"].values():
        pallet["suppliers"] = list(dict.fromkeys(supplier_name(name) for name in pallet["suppliers"]))
    return pallets


def _check_sources(root: Path, migration: Dict[str, Any]) -> None:
    hashes = migration.get("source_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("元データの照合値がありません")
    for relative, expected in hashes.items():
        path = (root / relative).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("元データのパスが作業フォルダ外です")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("元データが変更されています。移行案の再確認が必要です: " + relative)
    expected_cases = {str(path.relative_to(root)) for path in
                      (root / "test_programmer" / "test_cases").glob("*.json")}
    recorded_cases = {relative for relative in hashes
                      if (root / relative).parent == root / "test_programmer" / "test_cases"}
    if expected_cases != recorded_cases:
        raise ValueError("ケースが追加・削除されています。移行案の再確認が必要です")


def load_catalog(root: Path) -> Tuple[Dict[str, Any], str]:
    """保存済みカタログと変更検出用の版を取得する。"""
    revision = _revision(root)
    data = {key: _read_json(path) for key, path in _paths(root).items()
            if key != "cases" or path.exists()}
    validate_catalog(data)
    if "cases" in data:
        validate_staged_cases(data["cases"], data["parts"], catalog_pallets(root))
    _check_sources(root, data["migration"])
    if revision != _revision(root):
        raise ValueError("読み込み中にDBが更新されました。再読み込みしてください")
    return data, revision


def save_catalog(root: Path, data: Dict[str, Any], expected_revision: Optional[str]) -> str:
    """全ファイルを準備してから保存し、失敗時は変更済みファイルを戻す。"""
    normalized = normalize_catalog(data)
    validate_catalog(normalized)
    _check_sources(root, normalized["migration"])
    paths = {key: path for key, path in _paths(root).items() if key in normalized}
    if "cases" in normalized:
        validate_staged_cases(normalized["cases"], normalized["parts"], catalog_pallets(root))
    directory = paths["parts"].parent
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".save.lock"
    try:
        descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError("別の保存が処理中です。完了後に再実行してください") from error
    os.close(descriptor)
    staged: Dict[str, Path] = {}
    backups: Dict[str, Path] = {}
    replaced = []
    retain_backups = False
    try:
        if expected_revision is None:
            if any(path.exists() for path in paths.values()):
                raise ValueError("初期登録済みのDBは上書きしません")
        elif expected_revision != _revision(root):
            raise ValueError("確認後にDBが変更されました。再確認してください")
        if "cases" not in normalized and _paths(root)["cases"].exists():
            raise ValueError("保存済みの準備用ケースを省略できません")
        for key, path in paths.items():
            for content, collection in (
                (_encoded(normalized[key]), staged),
                (path.read_bytes() if path.exists() else None, backups),
            ):
                if content is None:
                    continue
                with tempfile.NamedTemporaryFile(dir=str(directory), prefix=".catalog-",
                                                 suffix=".tmp", delete=False) as temporary:
                    collection[key] = Path(temporary.name)
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
        _check_sources(root, normalized["migration"])
        try:
            for key, path in paths.items():
                os.replace(str(staged[key]), str(path))
                replaced.append(key)
        except OSError as error:
            rollback_errors = []
            for key in reversed(replaced):
                try:
                    if key in backups:
                        os.replace(str(backups[key]), str(paths[key]))
                    else:
                        paths[key].unlink()
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if rollback_errors:
                retain_backups = True
                raise OSError("保存と復元に失敗しました: {} / {}。復旧用コピー: {}".format(
                    error, "; ".join(rollback_errors),
                    ", ".join(str(path) for path in backups.values() if path.exists()))) from error
            raise
        return _revision(root)
    finally:
        for path in list(staged.values()) + ([] if retain_backups else list(backups.values())):
            if path.exists():
                path.unlink()
        lock.unlink()


def initialize_catalog(root: Path, preview_path: Path) -> Dict[str, Any]:
    """承認済み事前確認と現在の入力が一致するときだけ新DBを登録する。"""
    approved = _read_json(preview_path)
    current = build_preview(root)
    if approved != current:
        raise ValueError("承認対象の事前確認と現在の移行案が異なります。再確認してください")
    if current["counts"]["blockers"]:
        raise ValueError("移行を止める問題があるため登録できません")
    fields = ("id", "supplier_name", "box_name", "box_model_id", "lid_id")
    data = {
        "parts": {part["id"]: {key: part[key] for key in fields} for part in current["parts"]},
        "models": current["models"], "lids": current["lids"],
        "migration": {
            "schema_version": 1, "phase": "phase2_pending_activation",
            "source_sha256": current["source_sha256"],
            "legacy_model_mapping": current["model_mapping"], "model_name_history": {},
            "case_assignments": current["case_rows"], "approved_changes": current["changes"],
        },
    }
    save_catalog(root, data, None)
    return data


def prepare_cases(root: Path) -> Dict[str, Any]:
    """承認済み割当てから別保存の品番ケースを初期作成する。既存ケースは維持。"""
    data, revision = load_catalog(root)
    if "cases" in data:
        raise ValueError("準備用ケースは登録済みです。上書きしません")
    approval_path = root / "test_programmer" / "test_case_approval.json"
    approvals = _read_json(approval_path) if approval_path.exists() else None
    if approvals is not None and not isinstance(approvals, dict):
        raise ValueError("採用状態はオブジェクトが必要です")
    cases = {}
    rows_by_file: Dict[str, Any] = {}
    for row in data["migration"]["case_assignments"]:
        rows_by_file.setdefault(row["case_file"], []).append(row)
    for filename, rows in rows_by_file.items():
        original = _read_json(root / "test_programmer" / "test_cases" / filename)
        case_id = Path(filename).stem
        case = copy.deepcopy(original)
        case["name"] = case_id
        case["supplier_name"] = supplier_name(case["supplier_name"])
        case["box_list"] = [{"part_number": row["part_number"], "count": row["count"]}
                            for row in sorted(rows, key=lambda row: row["row"])]
        case["pallet"] = {key: case.get("pallet", {}).get(key, default) for key, default in
                          (("max_x_span", 1360), ("max_y_span", 1100), ("max_height", 1200))}
        cases[case_id] = case
    data["cases"] = {
        "schema_version": 1, "test_cases": cases,
        "approval_state": {key: True if approvals is None else approvals.get(key) is True
                           for key in cases},
    }
    data["migration"]["phase"] = "phase3_pending_algorithm"
    save_catalog(root, data, revision)
    return data["cases"]


def preview_model_rename(root: Path, old_name: str, new_name: str) -> Dict[str, Any]:
    """関連品番・ケースを表示し、確認後の保存に必要な照合番号を発行する。"""
    data, revision = load_catalog(root)
    old, new = normalize_id(old_name), normalize_id(new_name)
    if old not in data["models"]:
        raise ValueError("変更元のモデルがありません: " + old)
    if not new or old == new:
        raise ValueError("変更後は異なる空でないモデル名を指定してください")
    if new in data["models"] or new in data["migration"]["model_name_history"]:
        raise ValueError("変更後の名前は既存モデルまたは旧名称と重複しています: " + new)
    if new in data["migration"]["legacy_model_mapping"]:
        raise ValueError("変更後の名前は旧箱名称として使用されています: " + new)
    parts = sorted(part_id for part_id, part in data["parts"].items()
                   if part["box_model_id"] == old)
    if "cases" in data:
        cases = sorted(case_id + ".json" for case_id, case in data["cases"]["test_cases"].items()
                       if any(row["part_number"] in parts for row in case["box_list"]))
    else:
        cases = sorted({row["case_file"] for row in data["migration"]["case_assignments"]
                        if row["part_number"] in parts})
    lids = sorted(set(data["models"][old]["compatible_lids"])
                  | {data["parts"][part]["lid_id"] for part in parts})
    plan = dict(old_name=old, new_name=new, revision=revision,
                affected_parts=parts, affected_cases=cases, affected_lids=lids)
    plan["confirmation"] = hashlib.sha256(_encoded(plan)).hexdigest()
    return plan


def rename_model(root: Path, old_name: str, new_name: str, confirmation: str) -> Dict[str, Any]:
    """確認した案と同じDBに対してのみ、モデル名と全品番参照を一括変更する。"""
    plan = preview_model_rename(root, old_name, new_name)
    if confirmation != plan["confirmation"]:
        raise ValueError("確認番号が一致しません。変更内容を再確認してください")
    data, revision = load_catalog(root)
    if revision != plan["revision"]:
        raise ValueError("DBが変更されました。再確認してください")
    old, new = plan["old_name"], plan["new_name"]
    record = data["models"].pop(old)
    record["id"] = new
    data["models"][new] = record
    for part in data["parts"].values():
        if part["box_model_id"] == old:
            part["box_model_id"] = new
    for name in ("legacy_model_mapping", "model_name_history"):
        mapping = data["migration"][name]
        for previous, current in list(mapping.items()):
            if current == old:
                mapping[previous] = new
    data["migration"]["model_name_history"][old] = new
    save_catalog(root, data, revision)
    return plan


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("initialize", help="承認済み案から新DBを初期登録")
    initialize.add_argument("--preview", type=Path, required=True)
    commands.add_parser("check", help="DBと元データの一致を確認")
    commands.add_parser("prepare-cases", help="品番方式の準備用ケースを別保存で作成")
    for name in ("preview-rename", "rename"):
        command = commands.add_parser(name)
        command.add_argument("old_name")
        command.add_argument("new_name")
        if name == "rename":
            command.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        if args.command == "initialize":
            data = initialize_catalog(ROOT, args.preview)
            output = {"parts": len(data["parts"]), "models": len(data["models"]),
                      "lids": len(data["lids"]), "phase": data["migration"]["phase"]}
        elif args.command == "prepare-cases":
            bundle = prepare_cases(ROOT)
            output = {"cases": len(bundle["test_cases"]),
                      "approved": sum(bundle["approval_state"].values())}
        elif args.command == "check":
            data, revision = load_catalog(ROOT)
            output = {"parts": len(data["parts"]), "models": len(data["models"]),
                      "lids": len(data["lids"]), "case_rows": len(data["migration"]["case_assignments"]),
                      "staged_cases": len(data.get("cases", {}).get("test_cases", {})),
                      "revision": revision, "phase": data["migration"]["phase"]}
        elif args.command == "preview-rename":
            output = preview_model_rename(ROOT, args.old_name, args.new_name)
        else:
            output = rename_model(ROOT, args.old_name, args.new_name, args.confirm)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        print("品番方式のデータが対象です。旧方式のDB・ケースは変更していません。")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "DB処理に失敗しました: {}\n".format(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
