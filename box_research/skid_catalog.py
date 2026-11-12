"""KEY2単位の積載条件と、ケースからの参照解決。"""

import copy
import hashlib
import json
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from box_research.catalog_helpers import supplier_name
from box_research.database_validation import normalize_id, validate_case_pallet_reference


LIMIT_FIELDS = ("max_x_span", "max_y_span", "max_height")
SKID_FIELDS = ("supplier_name", "pallet_id", "pallet", "part_numbers")
SKID_ID_PATTERN = re.compile(r"[0-9]{4}[A-Z0-9](?:[A-Z0-9]{3})?[A-Z]")


def normalize_skid_id(value: str) -> str:
    value = normalize_id(value).upper()
    if not SKID_ID_PATTERN.fullmatch(value):
        raise ValueError("スキッドIDは仕入先4桁数字・工区1文字英数字・出荷場3文字英数字または空欄・コース1文字英字で指定してください")
    return value


def normalize_suppliers(records: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(records, dict):
        raise ValueError("仕入先対応表はオブジェクトが必要です")
    result = {}
    for key, record in records.items():
        if not isinstance(record, dict) or set(record) != {"id", "supplier_name"} or record["id"] != key:
            raise ValueError("仕入先対応表の数字とIDが一致しません")
        key = normalize_id(key)
        if not re.fullmatch(r"[0-9]{4}", key):
            raise ValueError("仕入先は4桁の半角数字で指定してください")
        if key in result:
            raise ValueError("正規化後の仕入先が重複しています: " + key)
        result[key] = dict(id=key, supplier_name=supplier_name(record["supplier_name"]))
    return result


def validate_suppliers(records: Dict[str, Any]) -> None:
    if normalize_suppliers(records) != records:
        raise ValueError("仕入先対応表は正規化済みの値で保存してください")
    if any(not record["supplier_name"] for record in records.values()):
        raise ValueError("仕入先名は空欄にできません")


def skid_snapshot(record: Dict[str, Any]) -> Dict[str, Any]:
    return {key: copy.deepcopy(record[key]) for key in SKID_FIELDS}


def normalize_skids(records: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(records, dict):
        raise ValueError("スキッドDBはオブジェクトが必要です")
    normalized = {}
    for key, record in records.items():
        if (not isinstance(record, dict) or record.get("id") != key
                or set(record) != {"id", *SKID_FIELDS, "updated_at", "history"}):
            raise ValueError("スキッドのキーとKEY2が一致しません")
        key = normalize_skid_id(key)
        if key in normalized:
            raise ValueError("正規化後のKEY2が重複しています: " + key)
        item = copy.deepcopy(record)
        item["id"] = key
        item["supplier_name"] = supplier_name(item.get("supplier_name"))
        if item["pallet_id"] is not None:
            item["pallet_id"] = normalize_id(item["pallet_id"])
        if not isinstance(item.get("part_numbers"), list):
            raise ValueError(key + ": 候補品番は配列が必要です")
        item["part_numbers"] = [normalize_id(value) for value in item["part_numbers"]]
        normalized[key] = item
    return normalized


def skid_incomplete(record: Dict[str, Any]) -> bool:
    return record["pallet_id"] is None or any(record["pallet"][key] is None for key in LIMIT_FIELDS)


def validate_skids(records: Dict[str, Any], parts: Dict[str, Any],
                   pallets: Dict[str, Any], suppliers: Dict[str, Any]) -> None:
    if not isinstance(records, dict):
        raise ValueError("スキッドDBはオブジェクトが必要です")
    for key, record in records.items():
        if (not isinstance(key, str) or not SKID_ID_PATTERN.fullmatch(key)
                or not isinstance(record, dict) or record.get("id") != key
                or set(record) != {"id", *SKID_FIELDS, "updated_at", "history"}):
            raise ValueError("スキッドDBのKEY2・項目が不正です")
        supplier = record["supplier_name"]
        if key[:4] not in suppliers or suppliers[key[:4]]["supplier_name"] != supplier:
            raise ValueError(key + ": 仕入先対応表に数字と仕入先名を登録してください")
        if not isinstance(supplier, str) or not supplier or supplier_name(supplier) != supplier:
            raise ValueError(key + ": 仕入先が不正です")
        candidates = record["part_numbers"]
        if (not isinstance(candidates, list) or not candidates
                or any(not isinstance(part, str) or part not in parts for part in candidates)
                or len(candidates) != len(set(candidates))):
            raise ValueError(key + ": 候補品番が不正・重複、または品番DBにありません")
        if any(parts[part]["supplier_name"] != supplier for part in candidates):
            raise ValueError(key + ": 候補品番とスキッドの仕入先が一致しません")
        limits = record["pallet"]
        if not isinstance(limits, dict) or set(limits) != set(LIMIT_FIELDS):
            raise ValueError(key + ": 荷山上限の3項目が必要です")
        for value in limits.values():
            if value is not None and (type(value) not in (int, float)
                                      or not math.isfinite(value) or value <= 0):
                raise ValueError(key + ": 荷山上限は未登録または0より大きい有限数値です")
        if (limits["max_x_span"] is not None and limits["max_y_span"] is not None
                and limits["max_x_span"] < limits["max_y_span"]):
            raise ValueError(key + ": 最大Lは最大W以上にしてください")
        if record["pallet_id"] is not None:
            validate_case_pallet_reference(key, record, pallets)
        _validate_history(key, record)


def _validate_history(key: str, record: Dict[str, Any]) -> None:
    history = record["history"]
    if not isinstance(history, list):
        raise ValueError(key + ": 変更履歴は配列が必要です")
    previous = None
    latest_id = None
    for entry in history:
        if (not isinstance(entry, dict)
                or set(entry) not in (
                    {"updated_at", "before", "after", "affected_cases"},
                    {"updated_at", "before", "after", "affected_cases", "previous_id", "skid_id"})
                or not isinstance(entry["updated_at"], str)
                or not isinstance(entry["after"], dict)
                or set(entry["after"]) != set(SKID_FIELDS)
                or entry["before"] != previous
                or not isinstance(entry["affected_cases"], list)
                or any(not isinstance(name, str) for name in entry["affected_cases"])):
            raise ValueError(key + ": 変更履歴の形式・連続性が不正です")
        if "previous_id" in entry:
            if (not isinstance(entry["previous_id"], str) or not entry["previous_id"]
                    or not isinstance(entry["skid_id"], str)
                    or not SKID_ID_PATTERN.fullmatch(entry["skid_id"])
                    or entry["previous_id"] == entry["skid_id"]):
                raise ValueError(key + ": ID変更履歴が不正です")
            if latest_id is not None and latest_id != entry["previous_id"]:
                raise ValueError(key + ": ID変更履歴の連続性が不正です")
            latest_id = entry["skid_id"]
        try:
            timestamp = datetime.fromisoformat(entry["updated_at"])
        except ValueError as error:
            raise ValueError(key + ": 更新日時が不正です") from error
        if timestamp.tzinfo is None:
            raise ValueError(key + ": 更新日時にはタイムゾーンが必要です")
        previous = entry["after"]
    if history:
        if previous != skid_snapshot(record) or record["updated_at"] != history[-1]["updated_at"]:
            raise ValueError(key + ": 現在の設定と変更履歴が一致しません")
        if latest_id is not None and latest_id != key:
            raise ValueError(key + ": 現在のIDと変更履歴が一致しません")
    elif record["updated_at"] != "":
        raise ValueError(key + ": 更新日時に対応する変更履歴がありません")


def resolve_skid_case(case: Dict[str, Any], catalog: Dict[str, Any]) -> Dict[str, Any]:
    """保存ケースを変更せず、現在のスキッド設定を計算用に展開する。"""
    skid_id = case.get("skid_id")
    if not isinstance(skid_id, str) or skid_id not in catalog["skids"]:
        raise ValueError("ケースのKEY2がスキッドDBにありません")
    skid = catalog["skids"][skid_id]
    if case.get("supplier_name") != skid["supplier_name"]:
        raise ValueError(skid_id + ": ケースとスキッドの仕入先が一致しません")
    if any(row["part_number"] not in skid["part_numbers"] for row in case["box_list"]):
        raise ValueError(skid_id + ": ケースの品番がスキッドの候補品番にありません")
    if skid_incomplete(skid):
        raise ValueError(skid_id + ": パレットまたは荷山上限が未登録のため計算できません")
    return dict(copy.deepcopy(case), pallet_id=skid["pallet_id"],
                pallet=copy.deepcopy(skid["pallet"]))


def skid_changes(current: Dict[str, Any], draft: Dict[str, Any],
                  renames: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    renames = {} if renames is None else renames
    previous_ids = {new: old for old, new in renames.items()}
    changes = []
    for key in sorted((set(current["skids"]) - set(renames)) | set(draft["skids"])):
        old_key = previous_ids.get(key, key)
        before = skid_snapshot(current["skids"][old_key]) if old_key in current["skids"] else None
        after = skid_snapshot(draft["skids"][key]) if key in draft["skids"] else None
        if before != after or key in previous_ids:
            affected = sorted(name for name, case in draft["cases"]["test_cases"].items()
                              if case["skid_id"] == key)
            change = dict(skid_id=key, before=before, after=after, affected_cases=affected)
            if key in previous_ids:
                change["old_skid_id"] = old_key
            changes.append(change)
    return changes


def skid_confirmation(revision: str, changes: list,
                       supplier_changes: Optional[list] = None) -> str:
    payload = json.dumps(dict(revision=revision, changes=changes, supplier_changes=supplier_changes or []),
                         ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def record_skid_changes(current: Dict[str, Any], draft: Dict[str, Any],
                         renames: Optional[Dict[str, str]] = None) -> None:
    renames = {} if renames is None else renames
    previous_ids = {new: old for old, new in renames.items()}
    timestamp = datetime.now().astimezone().isoformat(timespec="microseconds")
    for key, record in draft["skids"].items():
        old = current["skids"].get(previous_ids.get(key, key))
        if old is not None and (record["history"] != old["history"]
                                or record["updated_at"] != old["updated_at"]):
            raise ValueError(key + ": 更新日時・変更履歴は直接変更できません")
        if old is None and (record["history"] or record["updated_at"]):
            raise ValueError(key + ": 新規スキッドの履歴は保存時に作成します")
    for change in skid_changes(current, draft, renames):
        if change["after"] is None:
            continue
        record = draft["skids"][change["skid_id"]]
        record["updated_at"] = timestamp
        record["history"].append(dict(updated_at=timestamp,
                                     **{key: change[key] for key in
                                        ("before", "after", "affected_cases")}))
        if "old_skid_id" in change:
            record["history"][-1].update(previous_id=change["old_skid_id"], skid_id=change["skid_id"])


def apply_skid_renames(current: Dict[str, Any], draft: Dict[str, Any],
                       renames: Dict[str, str]) -> Dict[str, str]:
    if not isinstance(renames, dict):
        raise ValueError("ID変更の対応はオブジェクトが必要です")
    normalized = {}
    for old, new in renames.items():
        old, new = normalize_skid_id(old), normalize_skid_id(new)
        if old in normalized or old == new:
            raise ValueError("ID変更元が重複、または変更前後が同じです")
        if old not in current["skids"] or old in draft["skids"] or new not in draft["skids"]:
            raise ValueError("ID変更元・変更先のスキッドが一致しません")
        if new in current["skids"] or new in normalized.values():
            raise ValueError("変更後のスキッドIDは既に使われています: " + new)
        normalized[old] = new
    for case in draft["cases"]["test_cases"].values():
        if case["skid_id"] in normalized:
            case["skid_id"] = normalized[case["skid_id"]]
    return normalized


def apply_supplier_corrections(current: Dict[str, Any], draft: Dict[str, Any]) -> list:
    """仕入先名の訂正を関連DBへ揃える。同じ名前への複数数字も一緒に訂正する。"""
    changes = {}
    for key, old in current["suppliers"].items():
        if key in draft["suppliers"]:
            new_name = draft["suppliers"][key]["supplier_name"]
            old_name = old["supplier_name"]
            if new_name != old_name:
                if old_name in changes and changes[old_name] != new_name:
                    raise ValueError("同じ仕入先名を異なる名前へ同時に訂正できません")
                changes[old_name] = new_name
    if any(new in changes for new in changes.values()):
        raise ValueError("仕入先名の入替え・連鎖した訂正は分けて保存してください")
    reports = []
    for old, new in changes.items():
        affected = dict(affected_suppliers=[], affected_parts=[], affected_skids=[],
                        affected_cases=[], affected_pallets=[])
        for collection, field in (("suppliers", "affected_suppliers"), ("parts", "affected_parts"),
                                  ("skids", "affected_skids")):
            for key, record in draft[collection].items():
                previous = current[collection].get(key)
                if record["supplier_name"] == old or (
                        collection == "suppliers" and previous and previous["supplier_name"] == old):
                    if record["supplier_name"] not in (old, new):
                        raise ValueError("仕入先名の訂正内容が一致しません")
                    record["supplier_name"] = new
                    affected[field].append(key)
        for key, case in draft["cases"]["test_cases"].items():
            if case["supplier_name"] == old:
                case["supplier_name"] = new
                affected["affected_cases"].append(key)
        for key, pallet in draft["pallets"]["pallets"].items():
            if old in pallet["suppliers"]:
                pallet["suppliers"] = list(dict.fromkeys(new if name == old else name
                                                        for name in pallet["suppliers"]))
                affected["affected_pallets"].append(key)
        reports.append(dict(before=old, after=new, **{key: sorted(value) for key, value in affected.items()}))
    for key in sorted(set(current["suppliers"]) ^ set(draft["suppliers"])):
        old, new = current["suppliers"].get(key), draft["suppliers"].get(key)
        reports.append(dict(before=old["supplier_name"] if old else None,
                            after=new["supplier_name"] if new else None,
                            affected_suppliers=[key], affected_parts=[], affected_skids=[],
                            affected_cases=[], affected_pallets=[]))
    return reports
