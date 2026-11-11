"""サーバーに依存しないDB・テストケースの検証処理。"""

import math
import re
import unicodedata
from typing import Any, Dict


def normalize_id(value: str) -> str:
    """合意済みの文字だけを統一し、別の記号を不用意に同一視しない。"""
    if not isinstance(value, str):
        raise ValueError("IDは文字列で指定してください")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("IDに制御文字・不可視文字を含めることはできません")
    value = re.sub(
        r"[\uff66-\uff9f]+",
        lambda match: unicodedata.normalize("NFKC", match.group()), value,
    )
    table = {ord(char): ord(char) - 0xFEE0
             for char in "０１２３４５６７８９"
             "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
             "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"}
    table.update({ord("＃"): "#", ord("－"): "-", ord("　"): " "})
    return unicodedata.normalize("NFC", value.translate(table)).strip(" ")


def _canonical_text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value or normalize_id(value) != value:
        raise ValueError("{}: 空でない正規化済み文字列が必要です".format(label))


def _finite_dimension(record: Dict[str, Any], key: str, label: str,
                      allow_zero: bool = False) -> None:
    value = record.get(key)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero)):
        raise ValueError("{}: {}の寸法値が不正です".format(label, key))


def validate_catalog_databases(parts: Dict[str, Any], models: Dict[str, Any],
                               lids: Dict[str, Any]) -> None:
    """新DBの正規化・寸法・品番から箱モデルと固定蓋への参照を検証する。"""
    for label, records in (("品番DB", parts), ("箱モデルDB", models), ("蓋DB", lids)):
        validate_record_database(records, label)
        if not records:
            raise ValueError(label + "が空です")
        for key in records:
            _canonical_text(key, label)
    for lid_id, lid in lids.items():
        if lid.get("type") not in ("TP", "OTHER", "NONE"):
            raise ValueError(lid_id + ": 蓋の規格が不正です")
        none = lid["type"] == "NONE"
        if lid.get("fit_type") not in (("なし",) if none else ("外嵌め", "内嵌め")):
            raise ValueError(lid_id + ": 蓋の嵌め方が不正です")
        for key in ("length", "width", "thickness"):
            _finite_dimension(lid, key, lid_id, allow_zero=none)
            if none and lid[key] != 0:
                raise ValueError(lid_id + ": 無蓋の寸法は0です")
        if lid["length"] < lid["width"]:
            raise ValueError(lid_id + ": LはW以上にしてください")
    if sum(lid["type"] == "NONE" for lid in lids.values()) != 1:
        raise ValueError("無蓋は1件必要です")
    for model_id, model in models.items():
        if model.get("type") not in ("TP", "NON_TP"):
            raise ValueError(model_id + ": 箱の規格が不正です")
        for key in ("length", "width", "height", "fitting_depth", "rib_thickness"):
            _finite_dimension(model, key, model_id,
                              allow_zero=key in ("fitting_depth", "rib_thickness"))
        if model["length"] < model["width"] or model["fitting_depth"] >= model["height"]:
            raise ValueError(model_id + ": L/Wまたは嵌合深さと高さの関係が不正です")
        if (isinstance(model.get("top_support_points"), bool)
                or not isinstance(model.get("top_support_points"), int)
                or model["top_support_points"] not in (4, 5)):
            raise ValueError(model_id + ": 支持点数は4または5です")
        compatible = model.get("compatible_lids")
        if (not isinstance(compatible, list)
                or any(not isinstance(item, str) or item not in lids for item in compatible)
                or len(compatible) != len(set(compatible))):
            raise ValueError(model_id + ": 互換蓋が不正または重複しています")
    for part_id, part in parts.items():
        for field in ("supplier_name", "box_name", "box_model_id", "lid_id"):
            _canonical_text(part.get(field), part_id + "." + field)
        model = models.get(part["box_model_id"])
        lid = lids.get(part["lid_id"])
        if model is None or lid is None:
            raise ValueError(part_id + ": 箱モデルまたは蓋が存在しません")
        if lid["type"] != "NONE" and part["lid_id"] not in model["compatible_lids"]:
            raise ValueError(part_id + ": 固定蓋が箱モデルと互換ではありません")


def validate_part_case_references(case: Dict[str, Any], parts: Dict[str, Any]) -> None:
    """品番方式ケースの仕入先・数量・固定蓋を検証する（旧形式とは別入口）。"""
    _canonical_text(case.get("supplier_name"), "ケース仕入先")
    rows = case.get("box_list")
    if not isinstance(rows, list) or not rows:
        raise ValueError("ケースには箱行が必要です")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("ケース箱行はオブジェクトが必要です")
        part_id = row.get("part_number")
        if not isinstance(part_id, str) or part_id not in parts:
            raise ValueError("品番がDBにありません")
        part = parts[part_id]
        if case["supplier_name"] != part["supplier_name"]:
            raise ValueError(part_id + ": ケースと品番の仕入先が一致しません")
        count = row.get("count")
        if (isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 500):
            raise ValueError(part_id + ": 個数は1〜500の整数です")
        if "box_id" in row or ("lid_id" in row and row["lid_id"] != part["lid_id"]):
            raise ValueError(part_id + ": 箱・蓋は品番DBから自動決定します")


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
        if pallet["length"] < pallet["width"]:
            raise ValueError("Pallet {}: length L must be greater than or equal to width W".format(pallet_id))
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
