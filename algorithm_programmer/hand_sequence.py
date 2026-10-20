"""Reverse a support-preserving static depalletizing sequence."""

from copy import deepcopy
from typing import Any, Dict, List, Set

from algorithm_programmer.hand_collision import EPSILON, _check_pose, _prepare_result
from algorithm_programmer.hand_profile import CORNERS, HandGeometryRangeError, validate_profile
from algorithm_programmer.models import PlacedBox


SUPPORT_HEIGHT_TOLERANCE = 1.0
SEQUENCE_PRIORITY = "grasp_reference_x_desc_then_y_desc_then_original_order_then_corner"
LAYER_POLICY = "layer_index_desc_removal_asc_loading"


class HandSequenceError(ValueError):
    """A complete, verified loading sequence could not be generated."""

    def __init__(self, result: Dict[str, Any]):
        self.result = result
        reasons = "; ".join("#{}: {}".format(entry["original_order"], entry["reason"])
                            for entry in result["remaining"])
        super().__init__("ハンド干渉を考慮した配置順を生成できません: " + reasons)


def _support_graph(data: Dict[str, Any], boxes: List[PlacedBox]) -> Dict[int, Set[int]]:
    supports = {}
    sources = {source["order"]: source for source in data["boxes"]}
    for upper in boxes:
        if upper.z < -1e-4:
            raise ValueError("#{}: 箱底面がパレット上面より下です".format(upper.order))
        direct = set()
        if upper.z > 1e-4:
            for lower in boxes:
                if lower.order == upper.order or lower.z >= upper.z - EPSILON:
                    continue
                if abs(lower.top_z - (upper.z + upper.fitting_depth)) > SUPPORT_HEIGHT_TOLERANCE:
                    continue
                overlap_x = min(upper.max_x, lower.max_x) - max(upper.footprint_min_x, lower.footprint_min_x)
                overlap_y = min(upper.max_y, lower.max_y) - max(upper.footprint_min_y, lower.footprint_min_y)
                if overlap_x > EPSILON and overlap_y > EPSILON:
                    direct.add(lower.order)
            if not direct:
                raise ValueError("#{}: 配置形状から直接支持箱を確認できません".format(upper.order))
        reported = sources[upper.order].get("supported_by")
        if reported is not None:
            if (not isinstance(reported, list) or any(type(item) is not int for item in reported)
                    or len(set(reported)) != len(reported) or set(reported) != direct):
                raise ValueError("#{}: supported_by と配置形状の支持関係が一致しません".format(upper.order))
        supports[upper.order] = direct
    # Edges must descend in Z; check the actual graph as well before sequencing.
    resolved = set()
    while len(resolved) < len(boxes):
        ready = {order for order, lower in supports.items() if order not in resolved and lower <= resolved}
        if not ready:
            raise ValueError("支持関係に循環があります")
        resolved.update(ready)
    return supports


def generate_hand_sequence(data: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Remove each layer top-down by clear grasp-corner XY; reverse and verify.

    Compare feasible box/corner pairs by reference X/Y descending, then identity.
    Failure returns only a partial removal trace, never a partial loading plan.
    """
    validate_profile(profile)
    boxes, pallet_x, pallet_y = _prepare_result(data)
    layers = {}
    for source in data["boxes"]:
        layer = source.get("layer_index")
        if type(layer) is not int or layer < 0:
            raise ValueError("#{}: layer_index は0以上の整数が必要です".format(source["order"]))
        layers[source["order"]] = layer
    supports = _support_graph(data, boxes)
    for order, lower_orders in supports.items():
        if any(layers[lower] >= layers[order] for lower in lower_orders):
            raise ValueError("#{}: 支持箱の layer_index は上段箱より小さい必要があります".format(order))
    by_order = {box.order: box for box in boxes}
    priority = sorted(boxes, key=lambda box: (-box.footprint_min_x, -box.footprint_min_y, box.order))
    remaining = set(by_order)
    removal = []
    stalled = []
    while remaining:
        active_layer = max(layers[order] for order in remaining)
        stalled = []
        chosen = None
        chosen_priority = None
        for box in priority:
            if box.order not in remaining:
                continue
            if layers[box.order] != active_layer:
                stalled.append({
                    "original_order": box.order, "box_id": box.box_id,
                    "layer_index": layers[box.order], "status": "layer_waiting",
                    "supported_orders": [], "candidates": [],
                    "reason": "上層（layer_index={}）の取り出し完了待ち".format(active_layer),
                })
                continue
            dependents = sorted(order for order in remaining if box.order in supports[order])
            if dependents:
                stalled.append({
                    "original_order": box.order, "box_id": box.box_id, "layer_index": layers[box.order],
                    "status": "supporting", "supported_orders": dependents, "candidates": [],
                    "reason": "上に支持している箱が残っています",
                })
                continue
            candidates = []
            for corner in CORNERS:
                try:
                    check = _check_pose(boxes, pallet_x, pallet_y, profile, box, corner,
                                        obstacle_orders=remaining - {box.order})
                except HandGeometryRangeError as error:
                    candidates.append({"corner_id": corner, "status": "out_of_range",
                                       "reason": str(error), "check": None})
                    continue
                candidates.append({
                    "corner_id": corner, "status": "blocked" if check["has_interference"] else "clear",
                    "reason": "配置位置で干渉あり" if check["has_interference"] else "静的干渉なし",
                    "check": check,
                })
            clear = [candidate["check"] for candidate in candidates if candidate["status"] == "clear"]
            for check in clear:
                x, y, _ = check["reference_position"]
                candidate_priority = (-x, -y, box.order, CORNERS.index(check["corner_id"]))
                if chosen_priority is None or candidate_priority < chosen_priority:
                    chosen_priority = candidate_priority
                    chosen = {
                        "original_order": box.order, "box_id": box.box_id, "layer_index": active_layer,
                        "step": len(removal) + 1, "selected": check,
                    }
            if clear:
                continue
            out_of_range = all(candidate["status"] == "out_of_range" for candidate in candidates)
            stalled.append({
                "original_order": box.order, "box_id": box.box_id, "layer_index": active_layer,
                "status": "out_of_range" if out_of_range else "blocked",
                "reason": "全角がハンド設定範囲外" if out_of_range else "設定範囲内の全角で干渉",
                "supported_orders": [], "candidates": candidates,
            })
        if chosen is None:
            break
        removal.append(chosen)
        remaining.remove(chosen["original_order"])
    loading = []
    if not remaining:
        placed = set()
        new_orders = {entry["original_order"]: index for index, entry in enumerate(reversed(removal), 1)}
        for entry in reversed(removal):
            original = entry["original_order"]
            if not supports[original] <= placed:
                raise ValueError("逆順の支持関係再検証に失敗しました: #{}".format(original))
            check = _check_pose(boxes, pallet_x, pallet_y, profile, by_order[original],
                                entry["selected"]["corner_id"], obstacle_orders=placed)
            if check["has_interference"] or set(check["checked_orders"]) != set(entry["selected"]["checked_orders"]):
                raise ValueError("逆順の静的干渉再検証に失敗しました: #{}".format(original))
            loading.append({
                "original_order": original, "box_id": entry["box_id"], "step": new_orders[original],
                "layer_index": layers[original],
                "supported_by": sorted(new_orders[lower] for lower in supports[original]),
                "original_supported_by": sorted(supports[original]), "selected": check,
            })
            placed.add(original)
    return {
        "check_type": "reverse_depalletizing_static", "status": "complete" if not remaining else "stalled",
        "profile": deepcopy(profile), "priority": SEQUENCE_PRIORITY,
        "layer_policy": LAYER_POLICY,
        "corner_priority": list(CORNERS),
        "depalletizing": removal, "palletizing": loading,
        "remaining": stalled if remaining else [],
        "summary": {"total": len(boxes), "removed": len(removal), "remaining": len(remaining)},
        "reverse_verified": not remaining, "trajectory_checked": False,
        "positions_changed": False, "source_modified": False,
    }
