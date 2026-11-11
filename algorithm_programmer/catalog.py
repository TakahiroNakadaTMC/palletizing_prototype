"""品番数量の管理と、共通箱モデルによる配置計算を分離する（第4段階）。"""

from collections import Counter
from typing import Any, Dict, List, Tuple

from algorithm_programmer.models import BoxSpec, PalletSpec
from algorithm_programmer.palletizer import Palletizer
from box_research.database_validation import (
    validate_catalog_databases, validate_part_case_references,
)


def run_catalog_case(
    test_name: str,
    case: Dict[str, Any],
    catalog: Dict[str, Any],
    pallet: PalletSpec,
    revision: str,
) -> Dict[str, Any]:
    """モデル・蓋で形状を計算し、確定した積み順へ入力順に品番を配分する。

    同じ形状でも品番の数量は統合しない。返却率の平準化はまだ行わない。
    """
    parts, models, lids = catalog["parts"], catalog["models"], catalog["lids"]
    validate_catalog_databases(parts, models, lids)
    validate_part_case_references(case, parts)
    if any(set(row) != {"part_number", "count"} for row in case["box_list"]):
        raise ValueError("品番方式の箱行にはpart_numberとcountだけを指定してください")

    quantities: Dict[str, int] = {}
    grouped_counts: Dict[Tuple[str, str], int] = {}
    group_parts: Dict[Tuple[str, str], List[str]] = {}
    specs: Dict[Tuple[str, str], BoxSpec] = {}
    for row in case["box_list"]:
        part_id, count = row["part_number"], row["count"]
        part = parts[part_id]
        key = (part["box_model_id"], part["lid_id"])
        if part_id not in quantities:
            quantities[part_id] = 0
            group_parts.setdefault(key, []).append(part_id)
        quantities[part_id] += count
        grouped_counts[key] = grouped_counts.get(key, 0) + count
        if key not in specs:
            model, lid = models[key[0]], lids[key[1]]
            spec = BoxSpec.from_dict(model)
            spec.lid_id = key[1]
            spec.lid_width = lid["width"]
            spec.lid_length = lid["length"]
            spec.lid_thickness = lid["thickness"]
            spec.lid_fit_type = lid["fit_type"]
            specs[key] = spec

    engine = Palletizer(specs, pallet)
    result = engine.run(test_name, [
        {"box_id": model_id, "lid_id": lid_id, "count": count}
        for (model_id, lid_id), count in grouped_counts.items()
    ]).to_dict()

    result["boxes"].sort(key=lambda box: box["order"])
    placed_counts: Dict[str, int] = Counter()
    group_index = {key: 0 for key in group_parts}
    for box in result["boxes"]:
        key = (box["box_id"], box["lid_id"])
        if key not in group_parts:
            raise RuntimeError("計算結果に投入していない箱モデル・蓋が含まれています")
        candidates = group_parts[key]
        index = group_index[key]
        while index < len(candidates) and placed_counts[candidates[index]] >= quantities[candidates[index]]:
            index += 1
        if index == len(candidates):
            raise RuntimeError("計算結果の箱数が投入数量を超えています")
        group_index[key] = index
        part_id = candidates[index]
        placed_counts[part_id] += 1
        part = parts[part_id]
        box.update(
            part_number=part_id, box_model_id=key[0], box_id=part["box_name"],
            box_name=part["box_name"], supplier_name=part["supplier_name"],
        )

    by_order = {box["order"]: box for box in result["boxes"]}
    if sorted(by_order) != list(range(1, len(result["boxes"]) + 1)):
        raise RuntimeError("計算結果の積み順に欠落または重複があります")
    top_support = result["summary"]["top_support"]
    for field in ("support_boxes", "multi_corner_boxes"):
        for item in top_support.get(field, []):
            source = by_order[item["order"]]
            item.update({key: source[key] for key in (
                "box_id", "part_number", "supplier_name", "box_name", "box_model_id", "lid_id")})

    reasons: Dict[str, List[str]] = {}
    for item in result["unplaced_boxes"]:
        reasons.setdefault(item["box_id"], []).append(item["reason"])
    part_counts = []
    unplaced = []
    input_parts = []
    for part_id, input_count in quantities.items():
        part = parts[part_id]
        identity = dict(part_number=part_id, supplier_name=part["supplier_name"],
                        box_name=part["box_name"], box_id=part["box_name"],
                        box_model_id=part["box_model_id"], lid_id=part["lid_id"])
        placed = placed_counts[part_id]
        missing = input_count - placed
        input_parts.append(dict(identity, count=input_count))
        part_counts.append(dict(identity, input_count=input_count, placed_count=placed,
                                unplaced_count=missing))
        if missing:
            model_reasons = reasons.get(part["box_model_id"])
            if not model_reasons:
                raise RuntimeError("未配置箱に対応する計算上の理由がありません")
            unplaced.append(dict(identity, count=missing,
                                 reason=" / ".join(dict.fromkeys(model_reasons))))
    if sum(placed_counts.values()) != result["placed_boxes_count"]:
        raise RuntimeError("配置数と品番配分数が一致しません")
    if sum(item["count"] for item in unplaced) != result["unplaced_boxes_count"]:
        raise RuntimeError("未配置数と品番別未配置数が一致しません")

    result.update(
        schema_version=2, input_mode="part_number", catalog_revision=revision,
        supplier_name=case["supplier_name"], pallet_id=case.get("pallet_id"),
        algorithm_mode="single" if len(grouped_counts) == 1 else "mixed",
        allocation_method="input_order", input_parts=input_parts, part_counts=part_counts,
        input_box_variants=[
            {key: item[key] for key in (
                "part_number", "box_id", "box_name", "box_model_id", "lid_id")}
            for item in input_parts
        ],
        unplaced_boxes=unplaced,
    )
    return result
