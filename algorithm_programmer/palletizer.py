#!/usr/bin/env python3
"""
パレタイズ計算エンジン (palletizer.py)
HM-Palletizer:
1. 嵌合沈み込み計算 (fitting_depth)
2. TP規格モジュール嵌合段積み & 非TPコラム積み
3. 長辺<1360mm / 短辺800-1100mm 許容対応
4. 最高層四隅高さ一致 (Top 4-Corner Leveling)
5. トポロジカル積み順付番 (Order)
"""

import math
import copy
from collections import Counter
from typing import List, Dict, Tuple, Optional, Any
from algorithm_programmer.models import BoxSpec, PlacedBox, PalletSpec, PalletizeResult

CORNER_HEIGHT_TOLERANCE_MM = 3.0
TOP_CORNER_MARGIN_MM = 35.0
SMALL_EDGE_MAX_LENGTH_MM = 335.0
GEOMETRY_EPS_MM = 1e-3
POSITION_SERIALIZATION_MARGIN_MM = 0.02
MIXED_LAYER_SEARCH_WIDTH = 16

def calculate_max_layers(height: float, fitting_depth: float, max_height: float) -> int:
    """嵌合沈み込みを考慮した最大積載段数を算出"""
    if height <= 0 or max_height < height:
        return 0
    effective_h = height - fitting_depth
    if effective_h <= 0:
        return int(max_height // height)
    return int((max_height - height) // effective_h) + 1

def intersects_2d(x1: float, y1: float, w1: float, l1: float,
                  x2: float, y2: float, w2: float, l2: float, eps: float = 1e-4) -> bool:
    """2D矩形の交差（重なり）判定"""
    return not (x1 + w1 <= x2 + eps or x2 + w2 <= x1 + eps or
                y1 + l1 <= y2 + eps or y2 + l2 <= y1 + eps)

def check_collision_3d(b1: PlacedBox, x2: float, y2: float, z2: float,
                       w2: float, l2: float, h2: float, d2: float, eps: float = 1e-4) -> bool:
    """3D空間での干渉判定（嵌合深さ沈み込みを許容）"""
    if not intersects_2d(b1.footprint_min_x, b1.footprint_min_y,
                         b1.max_x - b1.footprint_min_x, b1.max_y - b1.footprint_min_y,
                         x2, y2, w2, l2, eps):
        return False

    b1_top = b1.z + b1.height
    box2_top = z2 + h2

    if z2 >= b1_top - d2 - eps:
        return False
    if b1.z >= box2_top - b1.fitting_depth - eps:
        return False

    return not (b1_top <= z2 + eps or box2_top <= b1.z + eps)

class Palletizer:
    def __init__(self, box_db: Dict[str, BoxSpec], pallet: Optional[PalletSpec] = None):
        self.box_db = box_db
        self.pallet = pallet or PalletSpec()

    def _column_stack_group(self, box_id: str, lid_id: str,
                            lid_fit_type: str) -> Optional[Tuple[str, str]]:
        spec = self.box_db.get(box_id)
        if spec is None:
            return None
        if spec.is_tp and lid_fit_type == "外嵌め":
            return "TP_EXTERNAL_LID", lid_id
        if not spec.is_tp:
            return "NON_TP", box_id
        return None

    def _column_stack_is_allowed(self, upper_spec: BoxSpec, upper: PlacedBox,
                                 lower_boxes: List[PlacedBox]) -> bool:
        upper_group = upper_spec.column_stack_group
        lower_direct = [
            lower for lower in lower_boxes
            if abs(lower.top_z - (upper.z + upper.fitting_depth)) <= 1.0
            and intersects_2d(
                upper.footprint_min_x, upper.footprint_min_y,
                upper.max_x - upper.footprint_min_x, upper.max_y - upper.footprint_min_y,
                lower.footprint_min_x, lower.footprint_min_y,
                lower.max_x - lower.footprint_min_x, lower.max_y - lower.footprint_min_y
            )
        ]
        lower_groups = {
            id(lower): self._column_stack_group(
                lower.box_id, lower.lid_id, lower.lid_fit_type
            )
            for lower in lower_direct
        }

        if upper_group is None:
            return not any(group is not None for group in lower_groups.values())

        matching = [
            lower for lower in lower_direct
            if lower_groups[id(lower)] == upper_group
            and abs(lower.footprint_min_x - upper.footprint_min_x) <= 0.01
            and abs(lower.footprint_min_y - upper.footprint_min_y) <= 0.01
            and abs(lower.max_x - upper.max_x) <= 0.01
            and abs(lower.max_y - upper.max_y) <= 0.01
        ]
        return len(matching) == 1 and len(lower_direct) == 1

    def _small_edges_within_overhang(self, boxes: List[PlacedBox], shift_x: float = 0.0,
                                     shift_y: float = 0.0) -> bool:
        limit = self.pallet.max_small_edge_overhang_mm - POSITION_SERIALIZATION_MARGIN_MM
        for box in boxes:
            if box.layer_index != 0:
                continue
            if box.width <= SMALL_EDGE_MAX_LENGTH_MM:
                min_x = box.footprint_min_x + shift_x
                max_x = box.max_x + shift_x
                if min_x < -limit or max_x > self.pallet.length + limit:
                    return False
            if box.length <= SMALL_EDGE_MAX_LENGTH_MM:
                min_y = box.footprint_min_y + shift_y
                max_y = box.max_y + shift_y
                if min_y < -limit or max_y > self.pallet.width + limit:
                    return False
        return True

    def _centered_shift(self, boxes: List[PlacedBox]) -> Tuple[float, float]:
        min_x = min(box.footprint_min_x for box in boxes)
        max_x = max(box.max_x for box in boxes)
        min_y = min(box.footprint_min_y for box in boxes)
        max_y = max(box.max_y for box in boxes)
        return (
            (self.pallet.length - (max_x - min_x)) / 2.0 - min_x,
            (self.pallet.width - (max_y - min_y)) / 2.0 - min_y
        )

    def _centered_small_edges_are_valid(self, boxes: List[PlacedBox]) -> bool:
        if not boxes:
            return True
        shift_x, shift_y = self._centered_shift(boxes)
        return self._small_edges_within_overhang(boxes, shift_x, shift_y)

    def _reorder_small_edges_within_rows(self, boxes: List[PlacedBox]) -> None:
        rows: Dict[Tuple[float, float], List[PlacedBox]] = {}
        for box in boxes:
            if box.layer_index != 0:
                continue
            row_key = (round(box.footprint_min_y, 2), round(box.max_y, 2))
            rows.setdefault(row_key, []).append(box)

        for row_boxes in rows.values():
            sorted_boxes = sorted(row_boxes, key=lambda box: box.footprint_min_x)
            runs: List[List[PlacedBox]] = []
            for box in sorted_boxes:
                if not runs or box.footprint_min_x > runs[-1][-1].max_x + GEOMETRY_EPS_MM:
                    runs.append([box])
                else:
                    runs[-1].append(box)

            for run in runs:
                constrained = [box for box in run if box.width <= SMALL_EDGE_MAX_LENGTH_MM]
                unconstrained = [box for box in run if box.width > SMALL_EDGE_MAX_LENGTH_MM]
                if not constrained or len(unconstrained) < 2:
                    continue

                ordered = [unconstrained[0]] + constrained + unconstrained[1:]
                cell_widths = {
                    id(box): box.max_x - box.footprint_min_x
                    for box in run
                }
                cursor = min(box.footprint_min_x for box in run)
                for box in ordered:
                    cell_width = cell_widths[id(box)]
                    box.x = round(cursor + (cell_width - box.width) / 2.0, 2)
                    cursor += cell_width

    def run(self, test_name: str, box_input_list: List[Dict[str, Any]], lid_db: Dict[str, Dict[str, Any]] = None) -> PalletizeResult:
        """テストケース投入リストを受け取り、単載または混載アルゴリズムを実行
        
        Args:
            test_name: テスト名
            box_input_list: 投入箱リスト [{"box_id": "TP-332", "count": 60, "lid_id": "蓋ID"}, ...]
            lid_db: 蓋DB。lid_id 省略時は type が "NONE" の蓋を使用
        """
        if lid_db is None:
            lid_db = {}

        input_boxes_count = sum(max(0, int(item.get("count", 1))) for item in box_input_list)

        default_lid_id = next(
            (lid_id for lid_id, lid_info in lid_db.items() if lid_info.get("type") == "NONE"),
            ""
        )
        
        expanded_boxes: List[BoxSpec] = []
        unplaced_boxes: List[Dict[str, Any]] = []
        
        for item in box_input_list:
            bid = item["box_id"]
            cnt = item.get("count", 1)
            lid_id = item.get("lid_id", default_lid_id)
            
            if bid in self.box_db:
                lid_info = lid_db.get(lid_id, {})  # 【NEW】蓋情報を取得
                for _ in range(cnt):
                    box = copy.copy(self.box_db[bid])
                    box.lid_id = lid_id
                    box.lid_width = float(lid_info.get("width", 0.0))
                    box.lid_length = float(lid_info.get("length", 0.0))
                    box.lid_thickness = float(lid_info.get("thickness", 0.0))
                    box.lid_fit_type = lid_info.get("fit_type", "なし")
                    expanded_boxes.append(box)
            elif cnt > 0:
                unplaced_boxes.append({
                    "box_id": bid,
                    "count": cnt,
                    "reason": "箱DBに型番が登録されていません"
                })

        if not expanded_boxes:
            return PalletizeResult(
                test_name=test_name,
                pallet=self.pallet,
                boxes=[],
                summary={"error": "No valid boxes provided"},
                unplaced_boxes=unplaced_boxes,
                input_boxes_count=input_boxes_count
            )

        unique_variants = set(b.pool_key for b in expanded_boxes)
        if len(unique_variants) == 1:
            placed, algorithm_unplaced = self.palletize_single(expanded_boxes)
        else:
            placed, algorithm_unplaced = self.palletize_mixed(expanded_boxes)
        unplaced_boxes.extend(algorithm_unplaced)

        # 最高層四隅高さ揃え処理
        placed, unplaced_boxes = self.level_top_four_corners(placed, unplaced_boxes)

        # トポロジカルソートで積み順 order を付番
        placed = self.assign_loading_orders(placed)

        # 荷姿サマリーの算出
        summary = self.calculate_summary(placed)

        return PalletizeResult(
            test_name=test_name,
            pallet=self.pallet,
            boxes=placed,
            summary=summary,
            unplaced_boxes=unplaced_boxes,
            input_boxes_count=input_boxes_count
        )

    # -------------------------------------------------------------------------
    # 1. 単載パレタイズ (Mono-load Palletizer)
    # -------------------------------------------------------------------------
    def palletize_single(self, boxes: List[BoxSpec], lids: List[Dict[str, Any]] = None) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        """単一の箱型番・蓋組み合わせをパレットに配置する。"""
        sample_box = boxes[0]
        w, l, h = sample_box.width, sample_box.length, sample_box.height
        depth = sample_box.fitting_depth
        rib = sample_box.rib_thickness
        effective_height = h + sample_box.lid_thickness
        footprint_w = sample_box.footprint_width
        footprint_l = sample_box.footprint_length

        max_layers = calculate_max_layers(effective_height, depth, self.pallet.max_height)
        candidate_patterns = self._generate_single_2d_patterns(footprint_w, footprint_l)

        best_pattern = None
        best_count_per_layer = 0

        for pattern in candidate_patterns:
            x_span = pattern["x_span"]
            y_span = pattern["y_span"]

            pattern_boxes = []
            for item in pattern["boxes"]:
                box_w, box_l = (w, l) if item["rot"] == 0 else (l, w)
                lid_w, lid_l = (sample_box.lid_width, sample_box.lid_length) if item["rot"] == 0 else (sample_box.lid_length, sample_box.lid_width)
                pattern_boxes.append(PlacedBox(
                    order=0, box_id=sample_box.id,
                    x=item["x"] + (item["w"] - box_w) / 2.0,
                    y=item["y"] + (item["l"] - box_l) / 2.0,
                    z=0.0, width=box_w, length=box_l, height=effective_height,
                    fitting_depth=depth, rib_thickness=rib, rotation=item["rot"],
                    layer_index=0, lid_width=lid_w, lid_length=lid_l,
                    lid_fit_type=sample_box.lid_fit_type
                ))
            if not (self.pallet.min_x_span <= x_span < self.pallet.max_x_span):
                continue
            if not (self.pallet.min_y_span <= y_span < self.pallet.max_y_span):
                continue

            centered_x = (self.pallet.length - x_span) / 2.0
            centered_y = (self.pallet.width - y_span) / 2.0
            if not self._small_edges_within_overhang(pattern_boxes, centered_x, centered_y):
                continue

            count_in_layer = len(pattern["boxes"])
            if count_in_layer > best_count_per_layer:
                best_count_per_layer = count_in_layer
                best_pattern = pattern

        if not best_pattern:
            return [], [{"box_id": sample_box.id, "count": len(boxes),
                         "reason": f"最下段の335mm以下の辺をパレット端から{self.pallet.max_small_edge_overhang_mm:g}mm未満に収められる配置がありません"}]

        placed_boxes: List[PlacedBox] = []
        total_needed = len(boxes)
        box_idx = 0

        x_span = best_pattern["x_span"]
        y_span = best_pattern["y_span"]
        offset_x = (self.pallet.length - x_span) / 2.0
        offset_y = (self.pallet.width - y_span) / 2.0
        unplaced_reason = "最大積載高さの上限に達しました"

        for layer in range(max_layers):
            layer_z = layer * (effective_height - depth)
            if layer_z + effective_height > self.pallet.max_height + 1e-4:
                unplaced_reason = "最大積載高さを超えるため配置できません"
                break

            layer_pattern = best_pattern["boxes"]
            if layer % 2 == 1 and best_pattern.get("invertible", False):
                layer_pattern = [
                    {
                        "x": x_span - (b["x"] + b["w"]),
                        "y": y_span - (b["y"] + b["l"]),
                        "w": b["w"],
                        "l": b["l"],
                        "rot": b["rot"]
                    }
                    for b in layer_pattern
                ]

            boxes_in_layer = len(layer_pattern)
            # 四隅が揃う完全な層のみを積む
            if box_idx + boxes_in_layer > total_needed and box_idx > 0:
                unplaced_reason = "最上段を一層分そろえられず、四隅高さ一致を保てません"
                break

            for b_pos in layer_pattern:
                if box_idx >= total_needed:
                    break

                box = boxes[box_idx]
                box_w, box_l = (w, l) if b_pos["rot"] == 0 else (l, w)
                lid_w, lid_l = (box.lid_width, box.lid_length) if b_pos["rot"] == 0 else (box.lid_length, box.lid_width)
                
                pb = PlacedBox(
                    order=box_idx + 1,
                    box_id=box.id,
                    x=round(offset_x + b_pos["x"] + (b_pos["w"] - box_w) / 2.0, 2),
                    y=round(offset_y + b_pos["y"] + (b_pos["l"] - box_l) / 2.0, 2),
                    z=round(layer_z, 2),
                    width=box_w,
                    length=box_l,
                    height=effective_height,
                    fitting_depth=depth,
                    rib_thickness=rib,
                    rotation=b_pos["rot"],
                    layer_index=layer,
                    lid_id=box.lid_id,
                    lid_thickness=box.lid_thickness,
                    lid_width=lid_w,
                    lid_length=lid_l,
                    lid_fit_type=box.lid_fit_type
                )
                placed_boxes.append(pb)
                box_idx += 1

            if box_idx >= total_needed:
                break

        unplaced_count = total_needed - box_idx
        unplaced = [{"box_id": sample_box.id, "count": unplaced_count, "reason": unplaced_reason}] if unplaced_count > 0 else []

        if not self._small_edges_within_overhang(placed_boxes):
            return [], [{"box_id": sample_box.id, "count": total_needed,
                         "reason": f"最下段の335mm以下の辺をパレット端から{self.pallet.max_small_edge_overhang_mm:g}mm未満に収められる配置がありません"}]

        return placed_boxes, unplaced

    def _generate_single_2d_patterns(self, w: float, l: float) -> List[Dict[str, Any]]:
        patterns = []
        max_x = self.pallet.max_x_span - 1.0  # 1359mm
        max_y = self.pallet.max_y_span - 1.0  # 1099mm

        nx1 = int(max_x // w)
        ny1 = int(max_y // l)
        for count_x in range(1, nx1 + 1):
            for count_y in range(1, ny1 + 1):
                boxes0 = [
                    {"x": ix * w, "y": iy * l, "w": w, "l": l, "rot": 0}
                    for ix in range(count_x) for iy in range(count_y)
                ]
                patterns.append({
                    "type": "grid_0",
                    "boxes": boxes0,
                    "x_span": count_x * w,
                    "y_span": count_y * l,
                    "invertible": True
                })

        nx2 = int(max_x // l)
        ny2 = int(max_y // w)
        for count_x in range(1, nx2 + 1):
            for count_y in range(1, ny2 + 1):
                boxes90 = [
                    {"x": ix * l, "y": iy * w, "w": l, "l": w, "rot": 90}
                    for ix in range(count_x) for iy in range(count_y)
                ]
                patterns.append({
                    "type": "grid_90",
                    "boxes": boxes90,
                    "x_span": count_x * l,
                    "y_span": count_y * w,
                    "invertible": True
                })

        for split_nx_0 in range(1, nx1 + 1):
            width_used_0 = split_nx_0 * w
            rem_width = max_x - width_used_0
            split_nx_90 = int(rem_width // l)
            if split_nx_90 > 0 and ny2 > 0:
                boxes_split = []
                for ix in range(split_nx_0):
                    for iy in range(ny1):
                        boxes_split.append({"x": ix * w, "y": iy * l, "w": w, "l": l, "rot": 0})
                for ix in range(split_nx_90):
                    for iy in range(ny2):
                        boxes_split.append({"x": width_used_0 + ix * l, "y": iy * w, "w": l, "l": w, "rot": 90})
                x_span_split = width_used_0 + split_nx_90 * l
                y_span_split = max(ny1 * l, ny2 * w)
                patterns.append({
                    "type": "split_x",
                    "boxes": boxes_split,
                    "x_span": x_span_split,
                    "y_span": y_span_split,
                    "invertible": True
                })

        for split_ny_0 in range(1, ny1 + 1):
            len_used_0 = split_ny_0 * l
            rem_len = max_y - len_used_0
            split_ny_90 = int(rem_len // w)
            if split_ny_90 > 0 and nx2 > 0:
                boxes_split_y = []
                for ix in range(nx1):
                    for iy in range(split_ny_0):
                        boxes_split_y.append({"x": ix * w, "y": iy * l, "w": w, "l": l, "rot": 0})
                for ix in range(nx2):
                    for iy in range(split_ny_90):
                        boxes_split_y.append({"x": ix * l, "y": len_used_0 + iy * w, "w": l, "l": w, "rot": 90})
                x_span_split_y = max(nx1 * w, nx2 * l)
                y_span_split_y = len_used_0 + split_ny_90 * w
                patterns.append({
                    "type": "split_y",
                    "boxes": boxes_split_y,
                    "x_span": x_span_split_y,
                    "y_span": y_span_split_y,
                    "invertible": True
                })

        patterns.sort(key=lambda p: (len(p["boxes"]), p["y_span"]), reverse=True)
        return patterns

    # -------------------------------------------------------------------------
    # 2. 混載パレタイズ (Mixed-load Palletizer)
    #    MSP-EP ハイブリッド方式:
    #      - Module-Aware Strip Packing (行分割 + 行内FFD詰め) を主アルゴリズムとし、
    #      - 残渣は Extreme Points 法（既配置箱の右端・下端から動的候補生成）で補完する。
    #    層ループは箱切れ/高さ超過/配置不能のいずれかでのみ終了し、中間層の四隅不一致で
    #    打ち切らない（四隅高さ揃えは最上段のみ level_top_four_corners で保証する）。
    # -------------------------------------------------------------------------
    def palletize_mixed(self, boxes: List[BoxSpec], lids: List[Dict[str, Any]] = None) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        """混載パレタイズ: MSP-EPハイブリッドによるレイヤー別パッキング
        
        Args:
            boxes: 投入箱リスト
            lids: 【NEW】各箱に対応する蓋情報リスト
        """
        placed_boxes: List[PlacedBox] = []

        if lids is not None:
            boxes = [copy.copy(box) for box in boxes]
            for box, lid in zip(boxes, lids):
                box.lid_id = lid.get("lid_id", box.lid_id)
                box.lid_width = float(lid.get("lid_width", box.lid_width))
                box.lid_length = float(lid.get("lid_length", box.lid_length))
                box.lid_thickness = float(lid.get("lid_thickness", box.lid_thickness))
                box.lid_fit_type = lid.get("fit_type", box.lid_fit_type)

        box_pool = sorted(
            boxes,
            key=lambda b: (b.footprint_width * b.footprint_length, b.height + b.lid_thickness),
            reverse=True
        )

        envelope = self._determine_mixed_envelope(box_pool)
        first_layers = []
        candidate_pool = [box for box in box_pool
                          if box.height + box.lid_thickness <= self.pallet.max_height + 1e-4]
        while candidate_pool:
            layer_height = self._choose_layer_height(candidate_pool)
            height_pool = [box for box in candidate_pool
                           if abs(box.height + box.lid_thickness - layer_height) <= 1.0]
            first_layers.extend(candidate[0] for candidate in self._mixed_layer_candidates(
                height_pool, 0.0, 0, [], envelope
            ))
            candidate_pool = [box for box in candidate_pool
                              if abs(box.height + box.lid_thickness - layer_height) > 1.0]
        first_layers.sort(key=lambda layer: self._mixed_layer_candidate_score([], layer), reverse=True)

        layouts = [self._palletize_mixed_layout(box_pool, envelope)]
        for first_layer in first_layers[:MIXED_LAYER_SEARCH_WIDTH]:
            layouts.append(self._palletize_mixed_layout(box_pool, envelope, first_layer))

        best_layout = layouts[0]
        best_score = None
        for placed, unplaced in layouts:
            placed, unplaced = self.level_top_four_corners(placed, unplaced)
            self._align_pallet_bounds(placed)
            summary = self.calculate_summary(placed)
            balanced = bool(placed) and self._mixed_layer_candidate_score([], placed)[0] == 1
            score = (int(summary["is_valid"] and balanced), len(placed),
                     -max((box.top_z for box in placed), default=0.0))
            if best_score is None or score > best_score:
                best_layout = placed, unplaced
                best_score = score
        return best_layout

    def _palletize_mixed_layout(self, pool: List[BoxSpec], envelope: Dict[str, float],
                                first_layer: Optional[List[PlacedBox]] = None
                                ) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        """最下段候補を起点に上段まで配置し、残箱を記録する。"""
        placed_boxes = [copy.copy(box) for box in first_layer] if first_layer else []
        box_pool = list(pool)
        if first_layer:
            consumed = Counter((box.box_id, box.lid_id) for box in first_layer)
            box_pool = []
            for box in pool:
                if consumed[box.pool_key] > 0:
                    consumed[box.pool_key] -= 1
                else:
                    box_pool.append(box)

        current_z = max(box.top_z for box in placed_boxes) - placed_boxes[0].fitting_depth if placed_boxes else 0.0
        if placed_boxes and current_z <= 0.0:
            current_z = max(box.top_z for box in placed_boxes)
        layer_idx = 1 if placed_boxes else 0
        stop_reason = None

        while box_pool and current_z < self.pallet.max_height:
            # 高さが異なる箱が同一層に混在すると、層の上面が四隅で不揃いになる
            # ため、この層で使う代表高さ(layer_h)を選び、同じ高さの箱だけを
            # この層のパッキング対象とする。現在の高さに収まらない箱種は残し、
            # 高さ制約を満たす箱種だけで代表高さを選ぶ。
            height_eligible_pool = [
                b for b in box_pool
                if current_z + b.height + b.lid_thickness <= self.pallet.max_height + 1e-4
            ]
            if not height_eligible_pool:
                stop_reason = "残箱を積むには最大積載高さを超えます"
                break

            layer_placed: List[PlacedBox] = []
            remaining_layer_pool: List[BoxSpec] = []
            selected_layer_pool: List[BoxSpec] = []
            best_layer_score = None
            candidate_pool = list(height_eligible_pool)
            while candidate_pool:
                layer_h = self._choose_layer_height(candidate_pool)
                layer_pool = [b for b in candidate_pool if abs(b.height + b.lid_thickness - layer_h) <= 1.0]
                candidate_placed, candidate_remaining = self._pack_mixed_layer(
                    layer_pool, current_z, layer_idx, placed_boxes, envelope
                )
                if candidate_placed and max(pb.top_z for pb in candidate_placed) <= self.pallet.max_height + 1e-4:
                    candidate_score = self._mixed_layer_candidate_score(placed_boxes, candidate_placed)
                    if best_layer_score is None or candidate_score > best_layer_score:
                        layer_placed = candidate_placed
                        remaining_layer_pool = candidate_remaining
                        selected_layer_pool = layer_pool
                        best_layer_score = candidate_score
                candidate_pool = [
                    b for b in candidate_pool
                    if abs(b.height + b.lid_thickness - layer_h) > 1.0
                ]

            carry_over_pool = [b for b in box_pool if b not in selected_layer_pool]
            if not layer_placed:
                # これ以上どの箱も配置できない（デッドロック回避）
                stop_reason = "配置スペース、支持率、箱の向きなどの制約を満たす場所がありません"
                break

            layer_top = max(pb.top_z for pb in layer_placed)
            if layer_top > self.pallet.max_height + 1e-4:
                # この層は積載高さを超過するため積まない
                stop_reason = "次の層を積むと最大積載高さを超えます"
                break

            placed_boxes.extend(layer_placed)
            box_pool = remaining_layer_pool + carry_over_pool
            layer_idx += 1

            # 次の層のZ基準 (直前の箱の上面 - fitting_depth)
            next_z = layer_top - layer_placed[0].fitting_depth
            if next_z <= current_z:
                next_z = layer_top
            current_z = next_z

        unplaced_map: Dict[str, int] = {}
        for b in box_pool:
            unplaced_map[b.id] = unplaced_map.get(b.id, 0) + 1
        if stop_reason is None and box_pool:
            stop_reason = "最大積載高さの上限に達しました"
        unplaced_boxes = [
            {"box_id": bid, "count": cnt, "reason": stop_reason or "配置可能な箱がありません"}
            for bid, cnt in unplaced_map.items()
        ]

        self._align_pallet_bounds(placed_boxes)
        return placed_boxes, unplaced_boxes

    def _choose_layer_height(self, pool: List[BoxSpec]) -> float:
        """現在の残り箱プールから、この層で使う代表高さを選ぶ。

        同一層内で高さの異なる箱が混在すると層の上面が四隅で不揃いになり
        `level_top_four_corners` の判定基準（最上段のみ四隅一致）を崩す
        原因になるため、層ごとに単一の高さグループのみを対象とする。
        代表高さは残数（総個数）が最も多い高さを優先し、同数の場合は
        低い箱を優先して高さの余裕を残す。
        """
        counts: Dict[float, int] = {}
        best_area: Dict[float, float] = {}
        for b in pool:
            h = round(b.height + b.lid_thickness, 1)
            counts[h] = counts.get(h, 0) + 1
            area = b.footprint_width * b.footprint_length
            if area > best_area.get(h, -1.0):
                best_area[h] = area

        return max(counts.keys(), key=lambda h: (counts[h], -h, best_area[h]))

    def _mixed_layer_candidate_score(self, placed_boxes: List[PlacedBox],
                                    candidate_boxes: List[PlacedBox]
                                    ) -> Tuple[int, int, float, int, float]:
        """四隅の高さを崩さず、配置数と次段の高さ余裕も考慮して層候補を評価する。"""
        boxes = placed_boxes + candidate_boxes
        min_x = min(box.footprint_min_x for box in boxes)
        max_x = max(box.max_x for box in boxes)
        min_y = min(box.footprint_min_y for box in boxes)
        max_y = max(box.max_y for box in boxes)

        corners = [
            [box for box in boxes if box.footprint_min_x <= min_x + TOP_CORNER_MARGIN_MM and
             box.footprint_min_y <= min_y + TOP_CORNER_MARGIN_MM],
            [box for box in boxes if box.max_x >= max_x - TOP_CORNER_MARGIN_MM and
             box.footprint_min_y <= min_y + TOP_CORNER_MARGIN_MM],
            [box for box in boxes if box.footprint_min_x <= min_x + TOP_CORNER_MARGIN_MM and
             box.max_y >= max_y - TOP_CORNER_MARGIN_MM],
            [box for box in boxes if box.max_x >= max_x - TOP_CORNER_MARGIN_MM and
             box.max_y >= max_y - TOP_CORNER_MARGIN_MM]
        ]
        corner_tops = [max(box.top_z for box in corner) for corner in corners if corner]
        corner_coverage = len(corner_tops)
        corner_spread = max(corner_tops) - min(corner_tops) if corner_coverage == 4 else float("inf")
        balanced_corners = int(corner_coverage == 4 and corner_spread <= CORNER_HEIGHT_TOLERANCE_MM)
        candidate_top = max(box.top_z for box in candidate_boxes)

        return (
            balanced_corners,
            corner_coverage,
            -corner_spread,
            len(candidate_boxes),
            -candidate_top
        )

    def _determine_mixed_envelope(self, pool: List[BoxSpec]) -> Dict[str, float]:
        """異なる箱寸法の行も組み合わせられる全層共通の探索範囲を返す。"""
        return {
            "x_span": self.pallet.max_x_span - 1.0,
            "y_span": self.pallet.max_y_span - 1.0
        }

    def _support_ratio(self, x: float, y: float, w: float, l: float,
                       base_z: float, fitting_depth: float,
                       lower_boxes: List[PlacedBox], tol: float = 1.0) -> float:
        """パレット直置き、または直下段箱に対する底面支持面積比率を算出"""
        if base_z <= 1e-3:
            return 1.0

        bottom_area = w * l
        if bottom_area <= 0:
            return 0.0

        total_support = 0.0
        for ob in lower_boxes:
            if abs(ob.top_z - (base_z + fitting_depth)) > tol:
                continue
            ix_min = max(x, ob.footprint_min_x)
            ix_max = min(x + w, ob.max_x)
            iy_min = max(y, ob.footprint_min_y)
            iy_max = min(y + l, ob.max_y)
            if ix_max > ix_min and iy_max > iy_min:
                total_support += (ix_max - ix_min) * (iy_max - iy_min)

        return total_support / bottom_area

    @staticmethod
    def _is_oversized_support(lower_w: float, lower_l: float, upper_w: float, upper_l: float,
                              tol: float = 1.0) -> bool:
        """下段箱が上段箱より幅・奥行きの両方とも大きいか判定する。

        下段（支持側）箱が上段（被支持側）箱よりも幅・奥行きの両方で大きい場合、
        上段箱が下段箱の縁からずれて安定した嵌合が期待できず、荷崩れの
        危険性があるため段積み不可とする。片方の寸法のみ大きい場合や
        同一サイズの場合は許容する。
        """
        return lower_w > upper_w + tol and lower_l > upper_l + tol

    def _has_oversized_support(self, x: float, y: float, w: float, l: float,
                               base_z: float, fitting_depth: float,
                               lower_boxes: List[PlacedBox], tol: float = 1.0) -> bool:
        """直下段の支持箱の中に、上段箱より幅・奥行き両方とも大きい箱が
        含まれるかを判定する（パレット直置きの場合は下段箱が無いのでFalse）。
        """
        if base_z <= 1e-3:
            return False

        for ob in lower_boxes:
            if abs(ob.top_z - (base_z + fitting_depth)) > tol:
                continue
            # 2D的に支持面へ関与しているか（重なりがあるか）
            ix_min = max(x, ob.footprint_min_x)
            ix_max = min(x + w, ob.max_x)
            iy_min = max(y, ob.footprint_min_y)
            iy_max = min(y + l, ob.max_y)
            if ix_max <= ix_min or iy_max <= iy_min:
                continue
            if self._is_oversized_support(ob.width, ob.length, w, l, tol):
                return True

        return False

    def _row_free_intervals(self, layer_boxes: List[PlacedBox], row_y: float,
                            row_depth: float, max_row_width: float,
                            tol: float = 1e-3) -> List[Tuple[float, float]]:
        """指定した行(Y帯域)における、既配置箱に占有されていないX区間を算出"""
        intervals = [(0.0, max_row_width)]
        row_top = row_y + row_depth

        for pb in layer_boxes:
            if pb.footprint_min_y < row_top - tol and pb.max_y > row_y + tol:
                new_intervals = []
                for (s, e) in intervals:
                    if pb.max_x <= s + tol or pb.footprint_min_x >= e - tol:
                        new_intervals.append((s, e))
                        continue
                    if pb.footprint_min_x > s + tol:
                        new_intervals.append((s, pb.footprint_min_x))
                    if pb.max_x < e - tol:
                        new_intervals.append((pb.max_x, e))
                intervals = new_intervals

        return [(s, e) for (s, e) in intervals if e - s > tol]

    def _eligible_row_items(self, pool_counter: Counter, id_to_spec: Dict[Tuple[str, str], BoxSpec],
                            row_depth: float, tol: float = 1.0) -> List[Tuple[BoxSpec, int, float, float]]:
        """行の深さ(row_depth)に適合する箱の(仕様, 回転, 幅, 奥行)候補を列挙"""
        eligible = []
        for pool_key, cnt in pool_counter.items():
            if cnt <= 0:
                continue
            spec = id_to_spec[pool_key]
            is_square = abs(spec.footprint_width - spec.footprint_length) <= tol
            if abs(spec.footprint_length - row_depth) <= tol:
                eligible.append((spec, 0, spec.footprint_width, spec.footprint_length))
            if not is_square and abs(spec.footprint_width - row_depth) <= tol:
                eligible.append((spec, 90, spec.footprint_length, spec.footprint_width))
        eligible.sort(key=lambda it: it[2], reverse=True)
        return eligible

    def _fill_row_intervals(self, intervals: List[Tuple[float, float]], row_y: float,
                           row_depth: float, pool_counter: Counter, id_to_spec: Dict[Tuple[str, str], BoxSpec],
                           base_z: float, layer_idx: int, lower_boxes: List[PlacedBox],
                           tol: float = 1e-3, row_match_tol: float = 1.0) -> List[PlacedBox]:
        """行の空きX区間を、在庫箱でFFD(First-Fit-Decreasing)的に詰める"""
        placed: List[PlacedBox] = []

        for (s, e) in intervals:
            x_cursor = s
            progress = True
            while progress and x_cursor < e - tol:
                progress = False
                eligible = self._eligible_row_items(pool_counter, id_to_spec, row_depth, row_match_tol)
                for spec, rot, w, l in eligible:
                    if pool_counter[spec.pool_key] <= 0:
                        continue
                    if x_cursor + w > e + tol:
                        continue
                    box_w, box_l = (spec.width, spec.length) if rot == 0 else (spec.length, spec.width)
                    box_x = x_cursor + (w - box_w) / 2.0
                    box_y = row_y + (l - box_l) / 2.0
                    lid_w, lid_l = (spec.lid_width, spec.lid_length) if rot == 0 else (spec.lid_length, spec.lid_width)
                    pb = PlacedBox(
                        order=0,
                        box_id=spec.id,
                        x=round(box_x, 2),
                        y=round(box_y, 2),
                        z=round(base_z, 2),
                        width=box_w,
                        length=box_l,
                        height=spec.height + spec.lid_thickness,
                        fitting_depth=spec.fitting_depth,
                        rib_thickness=spec.rib_thickness,
                        rotation=rot,
                        layer_index=layer_idx,
                        lid_id=spec.lid_id,
                        lid_thickness=spec.lid_thickness,
                        lid_width=lid_w,
                        lid_length=lid_l,
                        lid_fit_type=spec.lid_fit_type
                    )
                    if layer_idx > 0:
                        ratio = self._support_ratio(box_x, box_y, box_w, box_l, base_z, spec.fitting_depth, lower_boxes)
                        if ratio < 0.85 - 1e-6:
                            continue
                        if self._has_oversized_support(box_x, box_y, box_w, box_l, base_z, spec.fitting_depth, lower_boxes):
                            continue
                        if not self._column_stack_is_allowed(spec, pb, lower_boxes):
                            continue
                    placed.append(pb)
                    pool_counter[spec.pool_key] -= 1
                    x_cursor += w
                    progress = True
                    break

        return placed

    def _try_place_at(self, x: float, y: float, spec: BoxSpec, rot: int,
                      layer_boxes: List[PlacedBox], max_row_width: float, max_total_depth: float,
                      base_z: float, layer_idx: int, lower_boxes: List[PlacedBox],
                      tol: float = 1e-3) -> Optional[PlacedBox]:
        """指定座標・回転で箱を置けるか判定し、置ければPlacedBoxを返す"""
        footprint_w = spec.footprint_width if rot == 0 else spec.footprint_length
        footprint_l = spec.footprint_length if rot == 0 else spec.footprint_width
        box_w, box_l = (spec.width, spec.length) if rot == 0 else (spec.length, spec.width)
        lid_w, lid_l = (spec.lid_width, spec.lid_length) if rot == 0 else (spec.lid_length, spec.lid_width)

        if x < -tol or y < -tol or x + footprint_w > max_row_width + tol or y + footprint_l > max_total_depth + tol:
            return None

        for placed in layer_boxes:
            if intersects_2d(x, y, footprint_w, footprint_l,
                             placed.footprint_min_x, placed.footprint_min_y,
                             placed.max_x - placed.footprint_min_x, placed.max_y - placed.footprint_min_y):
                return None

        box_x = x + (footprint_w - box_w) / 2.0
        box_y = y + (footprint_l - box_l) / 2.0
        placed_box = PlacedBox(
            order=0,
            box_id=spec.id,
            x=round(box_x, 2),
            y=round(box_y, 2),
            z=round(base_z, 2),
            width=box_w,
            length=box_l,
            height=spec.height + spec.lid_thickness,
            fitting_depth=spec.fitting_depth,
            rib_thickness=spec.rib_thickness,
            rotation=rot,
            layer_index=layer_idx,
            lid_id=spec.lid_id,
            lid_thickness=spec.lid_thickness,
            lid_width=lid_w,
            lid_length=lid_l,
            lid_fit_type=spec.lid_fit_type
        )
        if layer_idx > 0:
            ratio = self._support_ratio(box_x, box_y, box_w, box_l, base_z, spec.fitting_depth, lower_boxes)
            if ratio < 0.85 - 1e-6:
                return None
            if self._has_oversized_support(box_x, box_y, box_w, box_l, base_z, spec.fitting_depth, lower_boxes):
                return None
            if not self._column_stack_is_allowed(spec, placed_box, lower_boxes):
                return None
        return placed_box

    # [廃止] Anchor Corners メソッド
    # 制約仕様に「パレット4隅への配置要件」は存在しない
    # 最上層の四隅高さ揃えは level_top_four_corners() で対応済み
    # def _anchor_corners(self, layer_boxes: List[PlacedBox], pool_counter: Counter,
    #                     id_to_spec: Dict[str, BoxSpec], max_row_width: float, max_total_depth: float,
    #                     base_z: float, layer_idx: int, lower_boxes: List[PlacedBox]) -> None:
    #     """層の四隅（上端を優先）に在庫箱を1個ずつ仮配置し、最上段になった場合でも
    #     四隅高さ揃えチェックを通過しやすくする。在庫が少ない最終層でも、
    #     連続した1行ではなく4隅individual配置になるためコーナー欠落を防げる。
    #     """
    #     # 上端(Y最大側)から埋めることで、行詰めが下から積み上がっても
    #     # 最終的に上端コーナーが空のまま残るリスクを減らす。
    #     corner_targets = [
    #         ("top", "left"), ("top", "right"),
    #         ("bottom", "left"), ("bottom", "right"),
    #     ]
    #
    #     for cy_mode, cx_mode in corner_targets:
    #         candidates = sorted(
    #             (bid for bid, cnt in pool_counter.items() if cnt > 0),
    #             key=lambda bid: id_to_spec[bid].width * id_to_spec[bid].length,
    #             reverse=True
    #         )
    #         for bid in candidates:
    #             spec = id_to_spec[bid]
    #             placed_here = False
    #             for rot in (0, 90):
    #                 w, l = (spec.width, spec.length) if rot == 0 else (spec.length, spec.width)
    #                 x = 0.0 if cx_mode == "left" else max_row_width - w
    #                 y = 0.0 if cy_mode == "bottom" else max_total_depth - l
    #                 pb = self._try_place_at(x, y, spec, rot, layer_boxes, max_row_width, max_total_depth,
    #                                         base_z, layer_idx, lower_boxes)
    #                 if pb is not None:
    #                     layer_boxes.append(pb)
    #                     pool_counter[bid] -= 1
    #                     placed_here = True
    #                     break
    #             if placed_here:
    #                 break

    def _ep_fill_layer(self, layer_boxes: List[PlacedBox], pool_counter: Counter,
                       id_to_spec: Dict[Tuple[str, str], BoxSpec], max_row_width: float, max_total_depth: float,
                       base_z: float, layer_idx: int, lower_boxes: List[PlacedBox]) -> None:
        """Extreme Points法によるフォールバック充填: 既配置箱の右端・下端＋原点を
        動的な候補位置とし、行詰めで埋まらなかった残渣を可能な限り充填する。
        """
        changed = True
        ep_round = 0
        while changed:
            ep_round += 1
            changed = False
            candidates = {(0.0, 0.0)}
            for pb in layer_boxes:
                candidates.add((round(pb.max_x, 2), round(pb.footprint_min_y, 2)))
                candidates.add((round(pb.footprint_min_x, 2), round(pb.max_y, 2)))
            sorted_candidates = sorted(candidates, key=lambda p: (p[1], p[0]))

            remaining_ids = sorted(
                (pool_key for pool_key, cnt in pool_counter.items() if cnt > 0),
                key=lambda pool_key: id_to_spec[pool_key].footprint_width * id_to_spec[pool_key].footprint_length,
                reverse=True
            )

            placed_this_round = False
            for pool_key in remaining_ids:
                spec = id_to_spec[pool_key]
                for (cx, cy) in sorted_candidates:
                    for rot in (0, 90):
                        pb = self._try_place_at(cx, cy, spec, rot, layer_boxes, max_row_width, max_total_depth,
                                                base_z, layer_idx, lower_boxes)
                        
                        if pb is not None:
                            old_positions = [(box, box.x) for box in layer_boxes]
                            layer_boxes.append(pb)
                            self._reorder_small_edges_within_rows(layer_boxes)
                            if not self._centered_small_edges_are_valid(layer_boxes):
                                layer_boxes.pop()
                                for box, old_x in old_positions:
                                    box.x = old_x
                                continue
                            pool_counter[pool_key] -= 1
                            placed_this_round = True
                            changed = True
                            break
                    if placed_this_round:
                        break
                if placed_this_round:
                    break

    def _pack_mixed_layer(self, pool: List[BoxSpec], base_z: float, layer_idx: int,
                          placed_so_far: List[PlacedBox], envelope: Dict[str, float]
                          ) -> Tuple[List[PlacedBox], List[BoxSpec]]:
        """複数の行組み合わせから四隅と配置数が良い層を選ぶ。"""
        candidates = self._mixed_layer_candidates(pool, base_z, layer_idx, placed_so_far, envelope)
        if not candidates:
            return [], pool
        return max(candidates, key=lambda candidate: self._mixed_layer_candidate_score(
            placed_so_far, candidate[0]
        ))

    def _mixed_layer_candidates(self, pool: List[BoxSpec], base_z: float, layer_idx: int,
                                placed_so_far: List[PlacedBox], envelope: Dict[str, float]
                                ) -> List[Tuple[List[PlacedBox], List[BoxSpec]]]:
        """残数を候補ごとに管理し、上限付きで行の組み合わせを探索する。"""
        if not pool:
            return []
        max_row_width = envelope["x_span"]
        max_total_depth = envelope["y_span"]
        id_to_spec = {box.pool_key: box for box in pool}
        lower_boxes = [box for box in placed_so_far if box.z < base_z - 1e-3] if layer_idx > 0 else []
        states = [(0.0, [], Counter(box.pool_key for box in pool))]
        completed = []

        while states:
            next_states = []
            for row_y, layer_boxes, remaining in states:
                depths = sorted({
                    round(dimension, 1)
                    for pool_key, count in remaining.items() if count > 0
                    for dimension in (id_to_spec[pool_key].footprint_width,
                                      id_to_spec[pool_key].footprint_length)
                    if 0 < dimension <= max_total_depth - row_y + 1e-3
                }, reverse=True)
                extended = False
                for depth in depths:
                    trial_counter = Counter(remaining)
                    intervals = self._row_free_intervals(layer_boxes, row_y, depth, max_row_width)
                    row_boxes = self._fill_row_intervals(
                        intervals, row_y, depth, trial_counter, id_to_spec,
                        base_z, layer_idx, lower_boxes, row_match_tol=GEOMETRY_EPS_MM
                    )
                    if not row_boxes:
                        continue
                    self._reorder_small_edges_within_rows(row_boxes)
                    candidate_boxes = layer_boxes + row_boxes
                    next_y = max(box.max_y for box in candidate_boxes)
                    if next_y > max_total_depth + 1e-3:
                        continue
                    if not self._centered_small_edges_are_valid(candidate_boxes):
                        continue
                    next_states.append((next_y, candidate_boxes, trial_counter))
                    extended = True
                if not extended and layer_boxes:
                    completed.append((row_y, layer_boxes, remaining))
            next_states.sort(key=lambda state: (
                len(state[1]),
                sum((box.max_x - box.footprint_min_x) * (box.max_y - box.footprint_min_y)
                    for box in state[1]),
                -state[0]
            ), reverse=True)
            states = next_states[:MIXED_LAYER_SEARCH_WIDTH]

        candidates = []
        signatures = set()
        greedy_boxes, greedy_remaining = self._pack_mixed_layer_greedy(
            pool, base_z, layer_idx, placed_so_far, envelope
        )
        if greedy_boxes:
            candidates.append((greedy_boxes, greedy_remaining))
        for _, layer_boxes, remaining in completed:
            layer_boxes = [copy.copy(box) for box in layer_boxes]
            trial_counter = Counter(remaining)
            self._ep_fill_layer(layer_boxes, trial_counter, id_to_spec, max_row_width,
                                max_total_depth, base_z, layer_idx, lower_boxes)
            signature = tuple((box.box_id, box.lid_id, box.x, box.y, box.rotation)
                              for box in layer_boxes)
            if signature in signatures:
                continue
            signatures.add(signature)
            counts_left = Counter(trial_counter)
            remaining_pool = []
            for box in pool:
                if counts_left[box.pool_key] > 0:
                    remaining_pool.append(box)
                    counts_left[box.pool_key] -= 1
            candidates.append((layer_boxes, remaining_pool))
        candidates.sort(key=lambda candidate: self._mixed_layer_candidate_score(
            placed_so_far, candidate[0]
        ), reverse=True)
        return candidates[:MIXED_LAYER_SEARCH_WIDTH]

    def _pack_mixed_layer_greedy(self, pool: List[BoxSpec], base_z: float, layer_idx: int,
                                 placed_so_far: List[PlacedBox], envelope: Dict[str, float]
                                 ) -> Tuple[List[PlacedBox], List[BoxSpec]]:
        """1つの層（レイヤー）をMSP-EPハイブリッドでパッキングする。

        Phase A: 廃止（四隅への先置きは行わない）
        Phase B: Module-Aware Strip Packing（行分割 + 行内FFD詰め）
        Phase C: Extreme Points法による残渣充填
        """
        if not pool:
            return [], pool

        max_row_width = envelope["x_span"]
        max_total_depth = envelope["y_span"]

        pool_counter: Counter = Counter(b.pool_key for b in pool)
        id_to_spec: Dict[Tuple[str, str], BoxSpec] = {}
        for b in pool:
            id_to_spec.setdefault(b.pool_key, b)

        # 上段の支持率判定に用いる「直下段」の箱リスト
        lower_boxes = [pb for pb in placed_so_far if pb.z < base_z - 1e-3] if layer_idx > 0 else []

        layer_boxes: List[PlacedBox] = []

        # Phase A: 四隅アンカー（廃止）
        # Anchor Corners の制約はパレット仕様に存在しない
        # 最上層の四隅高さ揃えは level_top_four_corners() で対応済み
        # self._anchor_corners(layer_boxes, pool_counter, id_to_spec, max_row_width, max_total_depth,
        #                     base_z, layer_idx, lower_boxes)

        # Phase B: 行分割 + 行内FFD詰め（ボトムアップ）
        # Phase B: 行分割 + 行内FFD詰め（ボトムアップ）
        y_cursor = 0.0
        phase_b_round = 0
        while y_cursor < max_total_depth - 1e-3:
            phase_b_round += 1
            remaining_ids = [pool_key for pool_key, cnt in pool_counter.items() if cnt > 0]
            if not remaining_ids:
                break

            depth_budget = max_total_depth - y_cursor
            
            candidate_depths = sorted(
                {round(id_to_spec[key].footprint_width, 1) for key in remaining_ids if id_to_spec[key].footprint_width <= depth_budget + 1.0} |
                {round(id_to_spec[key].footprint_length, 1) for key in remaining_ids if id_to_spec[key].footprint_length <= depth_budget + 1.0},
                reverse=True
            )

            best = None
            for d in candidate_depths:
                if y_cursor + d > max_total_depth + 1e-3:
                    continue
                
                intervals = self._row_free_intervals(layer_boxes, y_cursor, d, max_row_width)
                if not intervals:
                    continue
                trial_counter = Counter(pool_counter)
                row_boxes = self._fill_row_intervals(intervals, y_cursor, d, trial_counter, id_to_spec,
                                                     base_z, layer_idx, lower_boxes)
                if not row_boxes:
                    continue
                self._reorder_small_edges_within_rows(row_boxes)
                if not self._centered_small_edges_are_valid(layer_boxes + row_boxes):
                    continue
                
                fill = sum(rb.width for rb in row_boxes)
                if best is None or fill > best[0]:
                    best = (fill, d, row_boxes, trial_counter)

            if best is None:
                break

            _, d, row_boxes, trial_counter = best
            
            layer_boxes.extend(row_boxes)
            pool_counter = trial_counter
            y_cursor += d

        # Phase C: Extreme Points法による残渣充填
        self._ep_fill_layer(layer_boxes, pool_counter, id_to_spec, max_row_width, max_total_depth,
                           base_z, layer_idx, lower_boxes)

        if not layer_boxes:
            return [], pool

        # 消費されなかった箱をpoolから再構成
        counts_left = dict(pool_counter)
        remaining_pool: List[BoxSpec] = []
        for b in pool:
            if counts_left.get(b.pool_key, 0) > 0:
                remaining_pool.append(b)
                counts_left[b.pool_key] -= 1

        for idx, pb in enumerate(layer_boxes, start=1):
            pb.order = idx

        return layer_boxes, remaining_pool

    def _align_pallet_bounds(self, placed_boxes: List[PlacedBox]):
        if not placed_boxes:
            return

        min_x = min(pb.footprint_min_x for pb in placed_boxes)
        max_x = max(pb.max_x for pb in placed_boxes)
        x_span = max_x - min_x

        min_y = min(pb.footprint_min_y for pb in placed_boxes)
        max_y = max(pb.max_y for pb in placed_boxes)
        y_span = max_y - min_y

        shift_x, shift_y = self._centered_shift(placed_boxes)
        for box in placed_boxes:
            box.x = round(box.x + shift_x, 2)
            box.y = round(box.y + shift_y, 2)

    # -------------------------------------------------------------------------
    # 3. 最高層四隅高さ揃え処理 (Top 4-Corner Leveling)
    # -------------------------------------------------------------------------
    def level_top_four_corners(self, placed_boxes: List[PlacedBox],
                               unplaced_boxes: List[Dict[str, Any]]) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        if not placed_boxes:
            return placed_boxes, unplaced_boxes

        min_x = min(pb.footprint_min_x for pb in placed_boxes)
        max_x = max(pb.max_x for pb in placed_boxes)
        min_y = min(pb.footprint_min_y for pb in placed_boxes)
        max_y = max(pb.max_y for pb in placed_boxes)

        margin = TOP_CORNER_MARGIN_MM
        c1_boxes = [pb for pb in placed_boxes if pb.footprint_min_x <= min_x + margin and pb.footprint_min_y <= min_y + margin]
        c2_boxes = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.footprint_min_y <= min_y + margin]
        c3_boxes = [pb for pb in placed_boxes if pb.footprint_min_x <= min_x + margin and pb.max_y >= max_y - margin]
        c4_boxes = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.max_y >= max_y - margin]

        if not (c1_boxes and c2_boxes and c3_boxes and c4_boxes):
            return placed_boxes, unplaced_boxes

        top_c1 = max(pb.top_z for pb in c1_boxes)
        top_c2 = max(pb.top_z for pb in c2_boxes)
        top_c3 = max(pb.top_z for pb in c3_boxes)
        top_c4 = max(pb.top_z for pb in c4_boxes)

        min_corner_top = min(top_c1, top_c2, top_c3, top_c4)
        max_corner_top = max(top_c1, top_c2, top_c3, top_c4)
        overall_top = max(pb.top_z for pb in placed_boxes)

        if (abs(max_corner_top - min_corner_top) <= CORNER_HEIGHT_TOLERANCE_MM and
            abs(overall_top - max_corner_top) <= CORNER_HEIGHT_TOLERANCE_MM):
            return placed_boxes, unplaced_boxes

        target_level = min_corner_top
        leveled_boxes = []
        removed_count: Dict[str, int] = {}

        for pb in placed_boxes:
            if pb.top_z <= target_level + CORNER_HEIGHT_TOLERANCE_MM:
                leveled_boxes.append(pb)
            else:
                removed_count[pb.box_id] = removed_count.get(pb.box_id, 0) + 1

        unplaced_map = {item["box_id"]: dict(item) for item in unplaced_boxes}
        for bid, cnt in removed_count.items():
            item = unplaced_map.setdefault(bid, {"box_id": bid, "count": 0, "reason": ""})
            item["count"] += cnt
            reason = "最高層の四隅高さを揃えるため除外されました"
            if item["reason"] and reason not in item["reason"]:
                item["reason"] += " / " + reason
            elif not item["reason"]:
                item["reason"] = reason

        new_unplaced = [item for item in unplaced_map.values() if item["count"] > 0]

        return leveled_boxes, new_unplaced

    # -------------------------------------------------------------------------
    # 4. 積み順（Order）決定 & サマリー計算
    # -------------------------------------------------------------------------
    def assign_loading_orders(self, placed_boxes: List[PlacedBox]) -> List[PlacedBox]:
        sorted_boxes = sorted(
            placed_boxes,
            key=lambda b: (round(b.z, 2), round(b.y, 2), round(b.x, 2))
        )

        for idx, pb in enumerate(sorted_boxes, start=1):
            pb.order = idx
            supporting_orders = []
            if pb.z > 1e-4:
                for other in sorted_boxes:
                    if other.order >= pb.order:
                        break
                    if intersects_2d(pb.footprint_min_x, pb.footprint_min_y,
                                     pb.max_x - pb.footprint_min_x, pb.max_y - pb.footprint_min_y,
                                     other.footprint_min_x, other.footprint_min_y,
                                     other.max_x - other.footprint_min_x, other.max_y - other.footprint_min_y):
                        if abs(other.top_z - (pb.z + pb.fitting_depth)) <= 1.0:
                            supporting_orders.append(other.order)
            pb.supported_by = supporting_orders

        return sorted_boxes

    def calculate_summary(self, placed_boxes: List[PlacedBox]) -> Dict[str, Any]:
        if not placed_boxes:
            return {
                "total_boxes": 0,
                "total_layers": 0,
                "is_valid": False,
                "violations": ["No boxes placed"]
            }

        min_x = min(pb.footprint_min_x for pb in placed_boxes)
        max_x = max(pb.max_x for pb in placed_boxes)
        x_span = max_x - min_x

        min_y = min(pb.footprint_min_y for pb in placed_boxes)
        max_y = max(pb.max_y for pb in placed_boxes)
        y_span = max_y - min_y

        max_z = max(pb.top_z for pb in placed_boxes)
        layers = len(set(round(pb.z, 1) for pb in placed_boxes))

        pallet_vol = self.pallet.width * self.pallet.length * self.pallet.max_height
        box_vol = sum(pb.width * pb.length * pb.height for pb in placed_boxes)
        vol_efficiency = (box_vol / pallet_vol) * 100.0

        violations = []
        if max_z > self.pallet.max_height + 1e-4:
            violations.append(f"Max height exceeded: {max_z:.1f}mm > {self.pallet.max_height}mm")
        if x_span < self.pallet.min_x_span - 1e-4:
            violations.append(f"Long side span too small: {x_span:.1f}mm < {self.pallet.min_x_span}mm")
        if x_span >= self.pallet.max_x_span:
            violations.append(f"Long side span exceeded: {x_span:.1f}mm >= {self.pallet.max_x_span}mm")
        if y_span >= self.pallet.max_y_span:
            violations.append(f"Short side overhang exceeded: {y_span:.1f}mm >= {self.pallet.max_y_span}mm")
        if y_span < self.pallet.min_y_span - 1e-4:
            violations.append(f"Short side too small: {y_span:.1f}mm < {self.pallet.min_y_span}mm")

        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        if (abs(center_x - self.pallet.length / 2.0) > 0.01 or
            abs(center_y - self.pallet.width / 2.0) > 0.01):
            violations.append("Palletized load is not centered on the pallet")

        if not self._small_edges_within_overhang(placed_boxes):
            violations.append("Bottom-layer small-edge overhang is at least the configured limit")

        # 四隅高さチェック
        margin = TOP_CORNER_MARGIN_MM
        c1 = [pb for pb in placed_boxes if pb.footprint_min_x <= min_x + margin and pb.footprint_min_y <= min_y + margin]
        c2 = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.footprint_min_y <= min_y + margin]
        c3 = [pb for pb in placed_boxes if pb.footprint_min_x <= min_x + margin and pb.max_y >= max_y - margin]
        c4 = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.max_y >= max_y - margin]

        if c1 and c2 and c3 and c4:
            t1 = max(b.top_z for b in c1)
            t2 = max(b.top_z for b in c2)
            t3 = max(b.top_z for b in c3)
            t4 = max(b.top_z for b in c4)
            if not (abs(t1 - max_z) <= CORNER_HEIGHT_TOLERANCE_MM and
                    abs(t2 - max_z) <= CORNER_HEIGHT_TOLERANCE_MM and
                    abs(t3 - max_z) <= CORNER_HEIGHT_TOLERANCE_MM and
                    abs(t4 - max_z) <= CORNER_HEIGHT_TOLERANCE_MM):
                violations.append(f"Top 4-corners height mismatch: C1={t1:.1f}, C2={t2:.1f}, C3={t3:.1f}, C4={t4:.1f} (Max={max_z:.1f})")

        return {
            "total_boxes": len(placed_boxes),
            "total_layers": layers,
            "bounding_box": {
                "min_x": round(min_x, 2),
                "max_x": round(max_x, 2),
                "x_span": round(x_span, 2),
                "min_y": round(min_y, 2),
                "max_y": round(max_y, 2),
                "y_span": round(y_span, 2),
                "max_z": round(max_z, 2)
            },
            "volume_efficiency_percent": round(vol_efficiency, 2),
            "is_valid": len(violations) == 0,
            "violations": violations
        }
