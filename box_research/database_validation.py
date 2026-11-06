"""サーバーに依存しないDB・テストケースの検証処理。"""

import math
from typing import Any, Dict


STANDARD_PALLET_ID = "__STANDARD_1200_1000_130__"
STANDARD_PALLET = {
    "id": STANDARD_PALLET_ID,
    "model": "標準パレット（型番未指定）",
    "length": 1200,
    "width": 1000,
    "height": 130,
    "suppliers": [],
    "standard": True,
}


def validate_record_database(database: Dict[str, Any], name: str) -> None:
    """箱・蓋DBの形式と登録IDを検証する。"""
    if not isinstance(database, dict):
        raise ValueError("{} must be an object".format(name))
    for key, item in database.items():
        if not isinstance(item, dict) or item.get("id") != key:
            raise ValueError("{}: record id must match its key ({})".format(name, key))


def validate_box_lid_databases(boxes: Dict[str, Any], lids: Dict[str, Any]) -> None:
    """箱・蓋DBの形式と互換蓋の参照を検証する。"""
    validate_record_database(boxes, "boxes")
    validate_record_database(lids, "lids")
    if not any(lid.get("type") == "NONE" for lid in lids.values()):
        raise ValueError("Keep at least one no-lid (NONE) option")
    for box_id, box in boxes.items():
        compatible = box.get("compatible_lids", [])
        if not isinstance(compatible, list) or any(
            not isinstance(lid_id, str) or lid_id not in lids for lid_id in compatible
        ):
            raise ValueError("Unknown or invalid compatible_lids for {}".format(box_id))


def validate_pallet_database(data: Dict[str, Any]) -> Dict[str, Any]:
    """パレットDBの形式、寸法、仕入先、固定標準仕様を検証する。"""
    if not isinstance(data, dict) or set(data) != {"pallets"}:
        raise ValueError("Pallet database must contain a pallets object")
    pallets = data["pallets"]
    if not isinstance(pallets, dict):
        raise ValueError("pallets must be an object")
    if STANDARD_PALLET_ID not in pallets:
        raise ValueError("The fixed standard pallet record is required")
    for pallet_id, pallet in pallets.items():
        if (not isinstance(pallet_id, str) or not pallet_id
                or not isinstance(pallet, dict) or pallet.get("id") != pallet_id):
            raise ValueError("Pallet id must match its key")
        if not isinstance(pallet.get("model"), str) or not pallet["model"].strip():
            raise ValueError("Pallet {} requires a model".format(pallet_id))
        suppliers = pallet.get("suppliers")
        is_standard = pallet_id == STANDARD_PALLET_ID
        if (not isinstance(suppliers, list) or (not suppliers and not is_standard)
                or any(not isinstance(name, str) or not name.strip() for name in suppliers)
                or len(suppliers) != len(set(suppliers))):
            raise ValueError("Pallet {} requires unique supplier names".format(pallet_id))
        if is_standard and pallet != STANDARD_PALLET:
            raise ValueError("The standard pallet record is fixed and cannot be changed")
        if not is_standard and pallet.get("standard"):
            raise ValueError("Only the reserved standard pallet can be marked standard")
        for field in ("length", "width", "height"):
            value = pallet.get(field)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                raise ValueError("Pallet {}.{} must be a positive finite number".format(pallet_id, field))
    return data


def validate_case_references(
    case_id: str, case: Dict[str, Any], boxes: Dict[str, Any],
    lids: Dict[str, Any], pallet_db: Dict[str, Any],
) -> None:
    """ケース保存時に、画面と同じ箱・蓋・数量・パレット条件を確認する。"""
    description = case.get("description")
    if not isinstance(description, str) or not description:
        raise ValueError(f"テストケース {case_id}: テスト説明 / 検証目的を入力してください")
    rows = case.get("box_list")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"テストケース {case_id}: 少なくとも1つの箱を追加してください")
    for index, row in enumerate(rows, 1):
        label = f"テストケース {case_id} 箱行{index}"
        if not isinstance(row, dict):
            raise ValueError(f"{label}: 箱の指定はオブジェクトである必要があります")
        box_id, lid_id = row.get("box_id"), row.get("lid_id")
        if not isinstance(box_id, str) or box_id not in boxes:
            raise ValueError(f"{label}: 箱型番がDBにありません")
        count = row.get("count")
        if (isinstance(count, bool) or not isinstance(count, (int, float))
                or not 1 <= count <= 500 or int(count) != count):
            raise ValueError(f"{label}: 個数は1〜500の整数で入力してください")
        if not isinstance(lid_id, str) or lid_id not in lids:
            raise ValueError(f"{label}: 登録済みの蓋を選択してください")
        if (lids[lid_id].get("type") != "NONE"
                and lid_id not in boxes[box_id].get("compatible_lids", [])):
            raise ValueError(f"{label}: 選択した蓋はこの箱に対応していません")
    validate_case_pallet_reference(case_id, case, pallet_db)


def validate_case_pallet_reference(
    case_id: str, case: Dict[str, Any], pallet_db: Dict[str, Any],
) -> None:
    """パレットIDと仕入先を確認する。本体寸法はケースではなくDBを正とする。"""
    pallet_id = case.get("pallet_id")
    if pallet_id is None:
        raise ValueError(f"テストケース {case_id} のパレット型番または標準パレットを選択してください")
    pallets = pallet_db["pallets"]
    if not isinstance(pallet_id, str) or pallet_id not in pallets:
        raise ValueError(f"テストケース {case_id} のパレット型番がDBにありません")
    if (pallet_id != STANDARD_PALLET_ID
            and case.get("supplier_name") not in pallets[pallet_id]["suppliers"]):
        raise ValueError(f"テストケース {case_id} の仕入先とパレット型番が一致しません")
