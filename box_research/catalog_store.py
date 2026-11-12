"""Authoritative catalog and case storage."""

import argparse
import copy
import hashlib
import json
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
    validate_pallet_database,
)
from box_research.catalog_helpers import file_sha256, read_json as _read_json, supplier_name
from box_research.skid_catalog import (
    normalize_skids, record_skid_changes, skid_changes, skid_confirmation,
    skid_incomplete, validate_skids, normalize_skid_id, normalize_suppliers,
    validate_suppliers, apply_skid_renames, apply_supplier_corrections,
)

FILES = {
    "parts": "box_type_db.json", "models": "box_model_db.json",
    "lids": "lid_db.json", "migration": "migration.json", "skids": "skid_db.json",
    "suppliers": "supplier_db.json",
}


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _paths(root: Path) -> Dict[str, Path]:
    directory = root / "box_research" / "catalog"
    return {**{key: directory / filename for key, filename in FILES.items()},
            "cases": directory / "test_cases.json",
            "pallets": root / "box_research" / "pallet_db.json"}


def _revision(root: Path) -> str:
    hashes = {key: file_sha256(path) if path.exists() else None
              for key, path in _paths(root).items()}
    return hashlib.sha256(_encoded(hashes)).hexdigest()


def normalize_catalog(data: Dict[str, Any]) -> Dict[str, Any]:
    """入力文字を正規化する。同じIDへの衝突は上書きせず拒否する。"""
    required = set(FILES) | {"cases", "pallets"}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("品番・箱モデル・蓋・仕入先対応表・スキッド・ケース・パレット・移行履歴が必要です")
    result = copy.deepcopy(data)
    result["suppliers"] = normalize_suppliers(result["suppliers"])
    result["skids"] = normalize_skids(result["skids"])
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
            case["skid_id"] = normalize_skid_id(case.get("skid_id"))
            for row in case["box_list"]:
                row["part_number"] = normalize_id(row.get("part_number"))
    if "pallets" in result:
        database = result["pallets"]
        if not isinstance(database, dict) or set(database) != {"pallets"} or not isinstance(database["pallets"], dict):
            raise ValueError("palletsはオブジェクトが必要です")
        records = {}
        for key, pallet in database["pallets"].items():
            if not isinstance(pallet, dict) or pallet.get("id") != key:
                raise ValueError("pallets: キーとIDが一致しません")
            normalized = normalize_id(key)
            if normalized in records:
                raise ValueError("正規化後のパレット型番が重複しています: " + normalized)
            pallet["id"] = normalized
            pallet["suppliers"] = list(dict.fromkeys(
                supplier_name(name) for name in pallet.get("suppliers", [])))
            records[normalized] = pallet
        database["pallets"] = records
    return result


def validate_catalog(data: Dict[str, Any]) -> None:
    """Validate current catalog references while keeping migration data historical."""
    required = set(FILES) | {"cases", "pallets"}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("カタログの構成が不正です")
    validate_catalog_databases(data["parts"], data["models"], data["lids"])
    migration = data["migration"]
    if (not isinstance(migration, dict) or migration.get("schema_version") != 1
            or not isinstance(migration.get("phase"), str)):
        raise ValueError("移行情報の版または段階が不正です")
    if not isinstance(migration.get("legacy_model_mapping"), dict):
        raise ValueError("旧モデル対応表がありません")
    history = migration.get("model_name_history")
    if not isinstance(history, dict):
        raise ValueError("モデル名変更履歴がありません")
    for old, current in history.items():
        if (not isinstance(old, str) or not old or old in data["models"]
                or not isinstance(current, str) or current not in data["models"]):
            raise ValueError("モデル名変更履歴の参照先が不正です")
    validate_pallet_database(data["pallets"])
    pallets = copy.deepcopy(data["pallets"])
    for pallet in pallets["pallets"].values():
        pallet["suppliers"] = list(dict.fromkeys(
            supplier_name(name) for name in pallet["suppliers"]))
    validate_suppliers(data["suppliers"])
    validate_skids(data["skids"], data["parts"], pallets, data["suppliers"])
    if "cases" in data:
        validate_staged_cases(data["cases"], data["parts"], data["skids"])


def validate_staged_cases(bundle: Dict[str, Any], parts: Dict[str, Any],
                          skids: Dict[str, Any]) -> None:
    """Validate saved case definitions, quantities, and skid references."""
    if (not isinstance(bundle, dict) or set(bundle) != {"schema_version", "test_cases", "approval_state"}
            or bundle["schema_version"] != 2
            or not isinstance(bundle["test_cases"], dict)
            or not isinstance(bundle["approval_state"], dict)
            or set(bundle["test_cases"]) != set(bundle["approval_state"])):
        raise ValueError("ケースと実行対象状態の構成が不正です")
    for case_id, case in bundle["test_cases"].items():
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", case_id):
            raise ValueError("ケースIDは英数字・ハイフン・下線で指定してください")
        if (not isinstance(case, dict) or case.get("name") != case_id
                or set(case) != {"name", "description", "supplier_name", "skid_id", "box_list"}
                or not isinstance(case.get("description"), str) or not case["description"].strip()
                or type(bundle["approval_state"][case_id]) is not bool):
            raise ValueError(case_id + ": 名前・説明・採用状態が不正です")
        validate_part_case_references(case, parts)
        if any(set(row) != {"part_number", "count"} for row in case["box_list"]):
            raise ValueError(case_id + ": 箱行には品番と数量だけを保存してください")
        skid_id = case.get("skid_id")
        if not isinstance(skid_id, str) or skid_id not in skids:
            raise ValueError(case_id + ": KEY2がスキッドDBにありません")
        skid = skids[skid_id]
        if case["supplier_name"] != skid["supplier_name"]:
            raise ValueError(case_id + ": ケースとスキッドの仕入先が一致しません")
        if any(row["part_number"] not in skid["part_numbers"] for row in case["box_list"]):
            raise ValueError(case_id + ": 使用中の品番を候補から削除できません。先にケースを修正してください")


def catalog_pallets(root: Path, pallet_database: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read the physical pallet database and normalize supplier aliases for consumers."""
    pallets = validate_pallet_database(
        _read_json(root / "box_research" / "pallet_db.json") if pallet_database is None
        else copy.deepcopy(pallet_database))
    for pallet in pallets["pallets"].values():
        pallet["suppliers"] = list(dict.fromkeys(supplier_name(name) for name in pallet["suppliers"]))
    return pallets


def load_catalog(root: Path) -> Tuple[Dict[str, Any], str]:
    """保存済みカタログと変更検出用の版を取得する。"""
    revision = _revision(root)
    data = {key: _read_json(path) for key, path in _paths(root).items()
            if key != "cases" or path.exists()}
    validate_catalog(data)
    if revision != _revision(root):
        raise ValueError("読み込み中にDBが更新されました。再読み込みしてください")
    return data, revision


def save_catalog(root: Path, data: Dict[str, Any], expected_revision: Optional[str],
                 confirmation: Optional[str] = None,
                 skid_renames: Optional[Dict[str, str]] = None) -> str:
    """全ファイルを準備してから保存し、失敗時は変更済みファイルを戻す。"""
    return _save_catalog(root, data, expected_revision, confirmation=confirmation,
                         skid_renames=skid_renames)


def _check_new_cases(current: Dict[str, Any], draft: Dict[str, Any],
                      renames: Dict[str, str]) -> None:
    for name, case in draft["cases"]["test_cases"].items():
        old = current["cases"]["test_cases"].get(name)
        if (old is None or renames.get(old["skid_id"], old["skid_id"]) != case["skid_id"]) and skid_incomplete(
                draft["skids"][case["skid_id"]]):
            raise ValueError(name + ": 未登録のパレット・荷山上限を設定してからケースを作成してください")


def preview_skid_changes(root: Path, skids: Optional[Dict[str, Any]],
                         expected_revision: str,
                         updates: Optional[Dict[str, Any]] = None,
                         skid_renames: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    current, revision = load_catalog(root)
    if expected_revision != revision:
        raise ValueError("確認後にDBが変更されました。再確認してください")
    draft = copy.deepcopy(current)
    if skids is not None:
        draft["skids"] = skids
    if updates:
        draft.update(updates)
    draft = normalize_catalog(draft)
    renames = apply_skid_renames(current, draft, {} if skid_renames is None else skid_renames)
    supplier_changes = apply_supplier_corrections(current, draft)
    changes = skid_changes(current, draft, renames)
    record_skid_changes(current, draft, renames)
    validate_catalog(draft)
    _check_new_cases(current, draft, renames)
    return dict(changes=changes, supplier_changes=supplier_changes,
                confirmation=skid_confirmation(revision, changes, supplier_changes))


def _save_catalog(root: Path, data: Dict[str, Any], expected_revision: Optional[str],
                  rename: Optional[Tuple[str, str]] = None,
                  confirmation: Optional[str] = None,
                  skid_renames: Optional[Dict[str, str]] = None) -> str:
    normalized = normalize_catalog(data)
    paths = {key: path for key, path in _paths(root).items() if key in normalized}
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
            validate_catalog(normalized)
        elif expected_revision != _revision(root):
            raise ValueError("確認後にDBが変更されました。再確認してください")
        if expected_revision is not None:
            current, current_revision = load_catalog(root)
            if current_revision != expected_revision:
                raise ValueError("確認後にDBが変更されました。再確認してください")
            renames = apply_skid_renames(
                current, normalized, {} if skid_renames is None else skid_renames)
            supplier_changes = apply_supplier_corrections(current, normalized)
            changes = skid_changes(current, normalized, renames)
            if (changes or supplier_changes) and confirmation != skid_confirmation(
                    expected_revision, changes, supplier_changes):
                raise ValueError("スキッド変更の影響を確認してから保存してください")
            record_skid_changes(current, normalized, renames)
            if rename is None:
                if normalized["migration"] != current["migration"]:
                    raise ValueError("移行情報・モデル名変更履歴は通常保存で変更できません")
                removed = set(current["models"]) - set(normalized["models"])
                if any(part["box_model_id"] in removed for part in current["parts"].values()):
                    raise ValueError("使用中のモデルは通常保存で削除・名前変更できません。名前変更は確認画面から行ってください")
            elif normalized != normalize_catalog(_renamed_catalog(current, *rename)):
                raise ValueError("確認したモデル名変更以外の変更は保存できません")
            validate_catalog(normalized)
            _check_new_cases(current, normalized, renames)
        for key, path in paths.items():
            if expected_revision is not None and normalized[key] == current[key]:
                continue
            for content, collection in (
                (_encoded(normalized[key]), staged),
                (path.read_bytes() if path.exists() else None, backups),
            ):
                if content is None:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix=".catalog-",
                                                 suffix=".tmp", delete=False) as temporary:
                    collection[key] = Path(temporary.name)
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
        try:
            for key, path in paths.items():
                if key not in staged:
                    continue
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
    parts = sorted(part_id for part_id, part in data["parts"].items()
                   if part["box_model_id"] == old)
    cases = sorted(case_id + ".json" for case_id, case in data.get("cases", {}).get(
        "test_cases", {}).items()
        if any(row["part_number"] in parts for row in case["box_list"]))
    lids = sorted(set(data["models"][old]["compatible_lids"])
                  | {data["parts"][part]["lid_id"] for part in parts})
    plan = dict(old_name=old, new_name=new, revision=revision,
                affected_parts=parts, affected_cases=cases, affected_lids=lids)
    plan["confirmation"] = hashlib.sha256(_encoded(plan)).hexdigest()
    return plan


def _renamed_catalog(data: Dict[str, Any], old: str, new: str) -> Dict[str, Any]:
    data = copy.deepcopy(data)
    record = data["models"].pop(old)
    record["id"] = new
    data["models"][new] = record
    for part in data["parts"].values():
        if part["box_model_id"] == old:
            part["box_model_id"] = new
    for previous, current in list(data["migration"]["model_name_history"].items()):
        if current == old:
            data["migration"]["model_name_history"][previous] = new
    data["migration"]["model_name_history"][old] = new
    return data


def rename_model(root: Path, old_name: str, new_name: str, confirmation: str) -> Dict[str, Any]:
    """確認した案と同じDBに対してのみ、モデル名と全品番参照を一括変更する。"""
    plan = preview_model_rename(root, old_name, new_name)
    if confirmation != plan["confirmation"]:
        raise ValueError("確認番号が一致しません。変更内容を再確認してください")
    data, revision = load_catalog(root)
    if revision != plan["revision"]:
        raise ValueError("DBが変更されました。再確認してください")
    old, new = plan["old_name"], plan["new_name"]
    _save_catalog(root, _renamed_catalog(data, old, new), revision, (old, new))
    return plan


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="現行カタログと参照整合性を確認")
    for name in ("preview-rename", "rename"):
        command = commands.add_parser(name)
        command.add_argument("old_name")
        command.add_argument("new_name")
        if name == "rename":
            command.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check":
            data, revision = load_catalog(ROOT)
            output = {"parts": len(data["parts"]), "models": len(data["models"]),
                      "lids": len(data["lids"]),
                      "skids": len(data["skids"]),
                      "suppliers": len(data["suppliers"]),
                      "cases": len(data.get("cases", {}).get("test_cases", {})),
                      "revision": revision, "phase": data["migration"]["phase"]}
        elif args.command == "preview-rename":
            output = preview_model_rename(ROOT, args.old_name, args.new_name)
        else:
            output = rename_model(ROOT, args.old_name, args.new_name, args.confirm)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        print("品番カタログとケースを検証・更新しました。")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "DB処理に失敗しました: {}\n".format(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
