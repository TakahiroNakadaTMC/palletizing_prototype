"""Static final-pose hand checks; no trajectory or loading-order search."""

from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple

from algorithm_programmer.hand_profile import (
    CORNERS, HandGeometryRangeError, build_preview, number, validate_profile,
)
from algorithm_programmer.models import BoxSpec, PlacedBox, POSITION_REFERENCE


EPSILON = 1e-7


def _positive(value: Any, label: str) -> float:
    result = number(value, label)
    if result <= 0:
        raise ValueError("{}: 正数を指定してください".format(label))
    return result


def _placed_box(source: Dict[str, Any], reference: Optional[str]) -> PlacedBox:
    if not isinstance(source, dict):
        raise ValueError("箱データはオブジェクトで指定してください")
    order = source.get("order")
    if type(order) is not int or order < 1:
        raise ValueError("order は1以上の整数が必要です")
    rotation = source.get("rotation")
    if type(rotation) is not int or rotation not in (0, 90):
        raise ValueError("箱の回転は0°または90°が必要です")
    box_id = source.get("box_id")
    if not isinstance(box_id, str) or not box_id:
        raise ValueError("box_id が必要です")
    dimensions, position = source["dimensions"], source["position"]
    width = _positive(dimensions["width"], "箱X寸法")
    length = _positive(dimensions["length"], "箱Y寸法")
    height = _positive(dimensions["height"], "蓋込み高さ")
    depth = number(source.get("fitting_depth", 0), "嵌合深さ")
    if depth < 0 or depth >= height:
        raise ValueError("嵌合深さは0以上、箱高さ未満が必要です")
    thickness = number(source.get("lid_thickness", 0), "蓋厚")
    if thickness < 0 or thickness >= height:
        raise ValueError("蓋厚は0以上、蓋込み高さ未満が必要です")
    lid_dimensions = source.get("lid_dimensions", {})
    fit_type = source.get("lid_fit_type", "なし")
    if fit_type not in ("なし", "外嵌め", "内嵌め"):
        raise ValueError("未対応の蓋の嵌め方です")
    if thickness == 0 and fit_type == "なし":
        for key in ("width", "length"):
            if number(lid_dimensions.get(key, 0), "無蓋の寸法") < 0:
                raise ValueError("無蓋の寸法は0以上が必要です")
        lid_width, lid_length = width, length
    else:
        lid_width = _positive(lid_dimensions.get("width", width), "蓋X寸法")
        lid_length = _positive(lid_dimensions.get("length", length), "蓋Y寸法")
    placed = PlacedBox(
        order=order, box_id=box_id,
        x=number(position["x"], "箱X"), y=number(position["y"], "箱Y"),
        z=number(position["z"], "箱Z"),
        width=width, length=length, height=height,
        fitting_depth=depth, rib_thickness=0, rotation=rotation,
        lid_id=source.get("lid_id", ""), lid_thickness=thickness,
        lid_width=lid_width, lid_length=lid_length, lid_fit_type=fit_type,
    )
    if reference == POSITION_REFERENCE:
        placed.x += (placed.footprint_width - width) / 2
        placed.y += (placed.footprint_length - length) / 2
        placed.z -= height
    return placed


def _solids(box: PlacedBox) -> List[Dict[str, Any]]:
    solids = [{
        "kind": "box", "order": box.order, "box_id": box.box_id,
        "min": [box.x, box.y, box.z],
        "max": [box.x + box.width, box.y + box.length, box.top_z - box.lid_thickness],
    }]
    if box.lid_thickness > 0:
        x = box.x + (box.width - box.lid_width) / 2
        y = box.y + (box.length - box.lid_length) / 2
        solids.append({
            "kind": "lid", "order": box.order, "box_id": box.box_id,
            "min": [x, y, box.top_z - box.lid_thickness],
            "max": [x + box.lid_width, y + box.lid_length, box.top_z],
        })
    return solids


def _intersection(a: Dict[str, Any], b: Dict[str, Any],
                  margin: float = 0) -> Optional[Dict[str, List[float]]]:
    low = [max(a["min"][i] - margin, b["min"][i]) for i in range(3)]
    high = [min(a["max"][i] + margin, b["max"][i]) for i in range(3)]
    if all(high[i] - low[i] > EPSILON for i in range(3)):
        return {"min": low, "max": high}
    return None


def _prepare_result(data: Dict[str, Any]) -> Tuple[List[PlacedBox], float, float]:
    if not isinstance(data, dict):
        raise ValueError("配置結果はオブジェクトが必要です")
    reference = data.get("coordinate_reference")
    if reference not in (None, POSITION_REFERENCE):
        raise ValueError("未対応の配置座標基準です")
    sources = data.get("boxes")
    if not isinstance(sources, list) or not sources:
        raise ValueError("boxes に配置済みの箱が必要です")
    boxes = [_placed_box(source, reference) for source in sources]
    if len({box.order for box in boxes}) != len(boxes):
        raise ValueError("配置順orderが重複しています")
    pallet = data["pallet"]
    pallet_x = _positive(pallet["length"], "パレットX寸法")
    pallet_y = _positive(pallet["width"], "パレットY寸法")
    return sorted(boxes, key=lambda box: box.order), pallet_x, pallet_y


def check_static_hand(data: Dict[str, Any], profile: Dict[str, Any],
                      order: int, corner: str) -> Dict[str, Any]:
    """Check earlier orders and pallet at final pose, not the trajectory.

    Tangency is allowed. Clearance applies to other boxes and pallet only.
    Target contact is allowed, but actual target penetration is reported.
    """
    if type(order) is not int or order < 1:
        raise ValueError("確認するorderは1以上の整数が必要です")
    boxes, pallet_x, pallet_y = _prepare_result(data)
    target = next((box for box in boxes if box.order == order), None)
    if target is None:
        raise ValueError("指定された配置順の箱がありません")
    return _check_pose(boxes, pallet_x, pallet_y, profile, target, corner)


def _check_pose(boxes: List[PlacedBox], pallet_x: float, pallet_y: float,
                profile: Dict[str, Any], target: PlacedBox, corner: str,
                obstacle_orders: Optional[Set[int]] = None) -> Dict[str, Any]:
    order = target.order
    sx, sy = target.footprint_width, target.footprint_length
    local_x, local_y = (sy, sx) if target.rotation == 90 else (sx, sy)
    spec = BoxSpec(target.box_id, target.box_id, "TP", local_x, local_y,
                   target.height, 0, 0)
    preview = build_preview(profile, spec, target.rotation, corner)
    offset = [target.footprint_min_x, target.footprint_min_y, target.top_z]
    envelope = [
        dict(part, min=[part["min"][i] + offset[i] for i in range(3)],
             max=[part["max"][i] + offset[i] for i in range(3)])
        for part in preview["envelope"]
    ]
    earlier = sorted((box for box in boxes if (
        box.order < order if obstacle_orders is None else box.order in obstacle_orders
    ) and box.order != order), key=lambda box: box.order)
    obstacles = [solid for box in earlier for solid in _solids(box)]
    margin = preview["clearance"]
    lowest = min(part["min"][2] - margin for part in envelope)
    pallet_solid = {
        "kind": "pallet", "min": [0, 0, min(-1, lowest - 1)],
        "max": [pallet_x, pallet_y, 0],
    }
    collisions = []
    contacts = []
    for index, part in enumerate(envelope):
        for obstacle in obstacles + [pallet_solid]:
            overlap = _intersection(part, obstacle, margin)
            if overlap is not None:
                collisions.append({
                    "hand_part_index": index, "hand_part": part["name"],
                    "obstacle": obstacle, "overlap": overlap,
                    "clearance_only": _intersection(part, obstacle) is None,
                })
        for solid in _solids(target):
            overlap = _intersection(part, solid)
            if overlap is not None:
                collisions.append({
                    "hand_part_index": index, "hand_part": part["name"],
                    "obstacle": dict(solid, kind="target_" + solid["kind"]),
                    "overlap": overlap, "clearance_only": False,
                })
            else:
                touching = all(min(part["max"][i], solid["max"][i])
                               >= max(part["min"][i], solid["min"][i]) - EPSILON
                               for i in range(3))
                if touching:
                    contacts.append({"hand_part": part["name"], "target_part": solid["kind"]})
    return {
        "check_type": "static_final_pose",
        "order": order, "box_id": target.box_id, "corner_id": corner,
        "hand_yaw_deg": preview["hand_yaw_deg"],
        "reference_position": [preview["reference_position"][i] + offset[i] for i in range(3)],
        "envelope": envelope, "clearance": margin,
        "checked_orders": [box.order for box in earlier],
        "collisions": collisions, "target_contacts": contacts,
        "has_interference": bool(collisions),
        "trajectory_checked": False, "order_changed": False,
    }


def select_static_corners(data: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate all four corners in fixed order without skipping earlier boxes.

    An unresolved earlier box remains an obstacle for later orders. Invalid
    input aborts the batch explicitly; only equipment range errors are per-corner.
    """
    validate_profile(profile)
    boxes, pallet_x, pallet_y = _prepare_result(data)
    entries = []
    counts = {"selected": 0, "blocked": 0, "out_of_range": 0}
    for box in boxes:
        candidates = []
        for corner in CORNERS:
            try:
                check = _check_pose(boxes, pallet_x, pallet_y, profile, box, corner)
            except HandGeometryRangeError as error:
                candidates.append({
                    "corner_id": corner, "status": "out_of_range", "reason": str(error),
                    "check": None,
                })
                continue
            candidates.append({
                "corner_id": corner, "status": "blocked" if check["has_interference"] else "clear",
                "reason": "配置位置で干渉あり" if check["has_interference"] else "配置位置で干渉なし（経路未判定）",
                "check": check,
            })
        selected = next((entry["check"] for entry in candidates if entry["status"] == "clear"), None)
        if selected is not None:
            status, reason = "selected", "固定優先順で最初の干渉しない角を選択"
        elif all(entry["status"] == "out_of_range" for entry in candidates):
            status, reason = "out_of_range", "全角がハンド設定範囲外（専用ハンドの切替は未対応）"
        else:
            status, reason = "blocked", "設定範囲内の全角で干渉（範囲外の角は未判定）"
        counts[status] += 1
        entries.append({
            "order": box.order, "box_id": box.box_id, "status": status, "reason": reason,
            "selected": selected, "candidates": candidates,
        })
    return {
        "check_type": "static_corner_selection",
        "profile": deepcopy(profile), "corner_priority": list(CORNERS),
        "boxes": entries, "summary": dict(counts, total=len(entries)),
        "all_corners_selected": counts["selected"] == len(entries),
        "trajectory_checked": False, "order_changed": False,
        "positions_changed": False,
    }
