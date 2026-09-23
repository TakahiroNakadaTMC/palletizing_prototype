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
    if not intersects_2d(b1.x, b1.y, b1.width, b1.length, x2, y2, w2, l2, eps):
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

    def run(self, test_name: str, box_input_list: List[Dict[str, Any]]) -> PalletizeResult:
        """テストケース投入リストを受け取り、単載または混載アルゴリズムを実行"""
        expanded_boxes: List[BoxSpec] = []
        for item in box_input_list:
            bid = item["box_id"]
            cnt = item.get("count", 1)
            if bid in self.box_db:
                for _ in range(cnt):
                    expanded_boxes.append(self.box_db[bid])

        if not expanded_boxes:
            return PalletizeResult(
                test_name=test_name,
                pallet=self.pallet,
                boxes=[],
                summary={"error": "No valid boxes provided"},
                unplaced_boxes=[]
            )

        unique_ids = set(b.id for b in expanded_boxes)
        if len(unique_ids) == 1:
            placed, unplaced = self.palletize_single(expanded_boxes)
        else:
            placed, unplaced = self.palletize_mixed(expanded_boxes)

        # 最高層四隅高さ揃え処理
        placed, unplaced = self.level_top_four_corners(placed, unplaced)

        # トポロジカルソートで積み順 order を付番
        placed = self.assign_loading_orders(placed)

        # 荷姿サマリーの算出
        summary = self.calculate_summary(placed)

        return PalletizeResult(
            test_name=test_name,
            pallet=self.pallet,
            boxes=placed,
            summary=summary,
            unplaced_boxes=unplaced
        )

    # -------------------------------------------------------------------------
    # 1. 単載パレタイズ (Mono-load Palletizer)
    # -------------------------------------------------------------------------
    def palletize_single(self, boxes: List[BoxSpec]) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        sample_box = boxes[0]
        w, l, h = sample_box.width, sample_box.length, sample_box.height
        depth = sample_box.fitting_depth
        rib = sample_box.rib_thickness

        max_layers = calculate_max_layers(h, depth, self.pallet.max_height)
        candidate_patterns = self._generate_single_2d_patterns(w, l)

        best_pattern = None
        best_count_per_layer = 0

        for pattern in candidate_patterns:
            x_span = pattern["x_span"]
            y_span = pattern["y_span"]

            if x_span >= self.pallet.max_x_span:
                continue
            if not (self.pallet.min_y_span <= y_span < self.pallet.max_y_span):
                continue

            count_in_layer = len(pattern["boxes"])
            if count_in_layer > best_count_per_layer:
                best_count_per_layer = count_in_layer
                best_pattern = pattern

        if not best_pattern:
            best_pattern = candidate_patterns[0]

        placed_boxes: List[PlacedBox] = []
        total_needed = len(boxes)
        box_idx = 0

        x_span = best_pattern["x_span"]
        y_span = best_pattern["y_span"]
        offset_x = (self.pallet.width - x_span) / 2.0
        offset_y = (self.pallet.length - y_span) / 2.0

        for layer in range(max_layers):
            layer_z = layer * (h - depth)
            if layer_z + h > self.pallet.max_height + 1e-4:
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
                break

            for b_pos in layer_pattern:
                if box_idx >= total_needed:
                    break

                pb = PlacedBox(
                    order=box_idx + 1,
                    box_id=sample_box.id,
                    x=round(offset_x + b_pos["x"], 2),
                    y=round(offset_y + b_pos["y"], 2),
                    z=round(layer_z, 2),
                    width=b_pos["w"],
                    length=b_pos["l"],
                    height=h,
                    fitting_depth=depth,
                    rib_thickness=rib,
                    rotation=b_pos["rot"],
                    layer_index=layer
                )
                placed_boxes.append(pb)
                box_idx += 1

            if box_idx >= total_needed:
                break

        unplaced_count = total_needed - box_idx
        unplaced = [{"box_id": sample_box.id, "count": unplaced_count}] if unplaced_count > 0 else []

        return placed_boxes, unplaced

    def _generate_single_2d_patterns(self, w: float, l: float) -> List[Dict[str, Any]]:
        patterns = []
        max_x = self.pallet.max_x_span - 1.0  # 1359mm
        max_y = self.pallet.max_y_span - 1.0  # 1099mm

        nx1 = int(max_x // w)
        ny1 = int(max_y // l)
        boxes1 = []
        for ix in range(nx1):
            for iy in range(ny1):
                boxes1.append({"x": ix * w, "y": iy * l, "w": w, "l": l, "rot": 0})
        if boxes1:
            patterns.append({
                "type": "grid_0",
                "boxes": boxes1,
                "x_span": nx1 * w,
                "y_span": ny1 * l,
                "invertible": True
            })

        nx2 = int(max_x // l)
        ny2 = int(max_y // w)
        boxes2 = []
        for ix in range(nx2):
            for iy in range(ny2):
                boxes2.append({"x": ix * l, "y": iy * w, "w": l, "l": w, "rot": 90})
        if boxes2:
            patterns.append({
                "type": "grid_90",
                "boxes": boxes2,
                "x_span": nx2 * l,
                "y_span": ny2 * w,
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
    def palletize_mixed(self, boxes: List[BoxSpec]) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        """混載パレタイズ: MSP-EPハイブリッドによるレイヤー別パッキング"""
        placed_boxes: List[PlacedBox] = []

        box_pool = list(boxes)
        box_pool.sort(key=lambda b: (b.width * b.length, b.height), reverse=True)

        # 荷姿エンベロープ（全層で共通のX/Y作業範囲）を投入箱構成から一度だけ決定する。
        # 同じエンベロープを全層で使い回すことで、上段箱が常に下段箱の上に
        # 高い支持率で乗るようにし（構造的な支持率確保）、最上段の四隅も
        # 揃いやすくする。
        envelope = self._determine_mixed_envelope(box_pool)

        current_z = 0.0
        layer_idx = 0

        while box_pool and current_z < self.pallet.max_height:
            # 高さが異なる箱が同一層に混在すると、層の上面が四隅で不揃いになる
            # ため、この層で使う代表高さ(layer_h)を選び、同じ高さの箱だけを
            # この層のパッキング対象とする（異なる高さの箱は後続の層に持ち越す）。
            layer_h = self._choose_layer_height(box_pool)
            layer_pool = [b for b in box_pool if abs(b.height - layer_h) <= 1.0]
            carry_over_pool = [b for b in box_pool if abs(b.height - layer_h) > 1.0]

            layer_placed, remaining_layer_pool = self._pack_mixed_layer(
                layer_pool, current_z, layer_idx, placed_boxes, envelope
            )
            if not layer_placed:
                # これ以上どの箱も配置できない（デッドロック回避）
                break

            layer_top = max(pb.top_z for pb in layer_placed)
            if layer_top > self.pallet.max_height + 1e-4:
                # この層は積載高さを超過するため積まない
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
        unplaced_boxes = [{"box_id": bid, "count": cnt} for bid, cnt in unplaced_map.items()]

        self._align_pallet_bounds(placed_boxes)
        return placed_boxes, unplaced_boxes

    def _choose_layer_height(self, pool: List[BoxSpec]) -> float:
        """現在の残り箱プールから、この層で使う代表高さを選ぶ。

        同一層内で高さの異なる箱が混在すると層の上面が四隅で不揃いになり
        `level_top_four_corners` の判定基準（最上段のみ四隅一致）を崩す
        原因になるため、層ごとに単一の高さグループのみを対象とする。
        代表高さは残数（総個数）が最も多い高さを優先し、同数の場合は
        底面積が最大の箱の高さを優先する。
        """
        counts: Dict[float, int] = {}
        best_area: Dict[float, float] = {}
        for b in pool:
            h = round(b.height, 1)
            counts[h] = counts.get(h, 0) + 1
            area = b.width * b.length
            if area > best_area.get(h, -1.0):
                best_area[h] = area

        return max(counts.keys(), key=lambda h: (counts[h], best_area[h]))

    def _determine_mixed_envelope(self, pool: List[BoxSpec]) -> Dict[str, float]:
        """投入箱構成から全層共通のX/Y作業エンベロープを決定する。

        短辺方向 (Y) は、箱の代表寸法のうち短辺許容範囲 [min_y_span, max_y_span)
        に収まる最小のモジュール単位を選び、その整数倍を採用する。
        これにより異なる箱サイズが混在してもモジュール嵌合しやすい行分割が
        可能になる。
        """
        dims = set()
        for b in pool:
            dims.add(round(b.width, 1))
            dims.add(round(b.length, 1))

        max_depth_allowed = self.pallet.max_y_span - 1.0
        candidates = []
        for d in sorted(dims):
            if d <= 0 or d > max_depth_allowed:
                continue
            n = int(max_depth_allowed // d)
            span = n * d
            if self.pallet.min_y_span <= span < self.pallet.max_y_span:
                candidates.append((d, span))

        if candidates:
            # 最も細かいモジュール単位（複数箱種を混在させやすい）を優先
            _, best_span = min(candidates, key=lambda t: t[0])
        else:
            best_span = max_depth_allowed

        return {
            "x_span": self.pallet.max_x_span - 1.0,
            "y_span": best_span
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
            ix_min = max(x, ob.x)
            ix_max = min(x + w, ob.max_x)
            iy_min = max(y, ob.y)
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
            ix_min = max(x, ob.x)
            ix_max = min(x + w, ob.max_x)
            iy_min = max(y, ob.y)
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
            if pb.y < row_top - tol and pb.max_y > row_y + tol:
                new_intervals = []
                for (s, e) in intervals:
                    if pb.max_x <= s + tol or pb.x >= e - tol:
                        new_intervals.append((s, e))
                        continue
                    if pb.x > s + tol:
                        new_intervals.append((s, pb.x))
                    if pb.max_x < e - tol:
                        new_intervals.append((pb.max_x, e))
                intervals = new_intervals

        return [(s, e) for (s, e) in intervals if e - s > tol]

    def _eligible_row_items(self, pool_counter: Counter, id_to_spec: Dict[str, BoxSpec],
                            row_depth: float, tol: float = 1.0) -> List[Tuple[BoxSpec, int, float, float]]:
        """行の深さ(row_depth)に適合する箱の(仕様, 回転, 幅, 奥行)候補を列挙"""
        eligible = []
        for bid, cnt in pool_counter.items():
            if cnt <= 0:
                continue
            spec = id_to_spec[bid]
            is_square = abs(spec.width - spec.length) <= tol
            if abs(spec.length - row_depth) <= tol:
                eligible.append((spec, 0, spec.width, spec.length))
            if not is_square and abs(spec.width - row_depth) <= tol:
                eligible.append((spec, 90, spec.length, spec.width))
        eligible.sort(key=lambda it: it[2], reverse=True)
        return eligible

    def _fill_row_intervals(self, intervals: List[Tuple[float, float]], row_y: float,
                           row_depth: float, pool_counter: Counter, id_to_spec: Dict[str, BoxSpec],
                           base_z: float, layer_idx: int, lower_boxes: List[PlacedBox],
                           tol: float = 1e-3) -> List[PlacedBox]:
        """行の空きX区間を、在庫箱でFFD(First-Fit-Decreasing)的に詰める"""
        placed: List[PlacedBox] = []

        for (s, e) in intervals:
            x_cursor = s
            progress = True
            while progress and x_cursor < e - tol:
                progress = False
                eligible = self._eligible_row_items(pool_counter, id_to_spec, row_depth)
                for spec, rot, w, l in eligible:
                    if pool_counter[spec.id] <= 0:
                        continue
                    if x_cursor + w > e + tol:
                        continue
                    if layer_idx > 0:
                        ratio = self._support_ratio(x_cursor, row_y, w, l, base_z, spec.fitting_depth, lower_boxes)
                        if ratio < 0.85 - 1e-6:
                            continue
                        if self._has_oversized_support(x_cursor, row_y, w, l, base_z, spec.fitting_depth, lower_boxes):
                            continue
                    pb = PlacedBox(
                        order=0,
                        box_id=spec.id,
                        x=round(x_cursor, 2),
                        y=round(row_y, 2),
                        z=round(base_z, 2),
                        width=w,
                        length=l,
                        height=spec.height,
                        fitting_depth=spec.fitting_depth,
                        rib_thickness=spec.rib_thickness,
                        rotation=rot,
                        layer_index=layer_idx
                    )
                    placed.append(pb)
                    pool_counter[spec.id] -= 1
                    x_cursor += w
                    progress = True
                    break

        return placed

    def _try_place_at(self, x: float, y: float, spec: BoxSpec, rot: int,
                      layer_boxes: List[PlacedBox], max_row_width: float, max_total_depth: float,
                      base_z: float, layer_idx: int, lower_boxes: List[PlacedBox],
                      tol: float = 1e-3) -> Optional[PlacedBox]:
        """指定座標・回転で箱を置けるか判定し、置ければPlacedBoxを返す"""
        w, l = (spec.width, spec.length) if rot == 0 else (spec.length, spec.width)
        if x < -tol or y < -tol or x + w > max_row_width + tol or y + l > max_total_depth + tol:
            return None
        for pb in layer_boxes:
            if intersects_2d(x, y, w, l, pb.x, pb.y, pb.width, pb.length):
                return None
        if layer_idx > 0:
            ratio = self._support_ratio(x, y, w, l, base_z, spec.fitting_depth, lower_boxes)
            if ratio < 0.85 - 1e-6:
                return None
            if self._has_oversized_support(x, y, w, l, base_z, spec.fitting_depth, lower_boxes):
                return None
        return PlacedBox(
            order=0,
            box_id=spec.id,
            x=round(x, 2),
            y=round(y, 2),
            z=round(base_z, 2),
            width=w,
            length=l,
            height=spec.height,
            fitting_depth=spec.fitting_depth,
            rib_thickness=spec.rib_thickness,
            rotation=rot,
            layer_index=layer_idx
        )

    def _anchor_corners(self, layer_boxes: List[PlacedBox], pool_counter: Counter,
                        id_to_spec: Dict[str, BoxSpec], max_row_width: float, max_total_depth: float,
                        base_z: float, layer_idx: int, lower_boxes: List[PlacedBox]) -> None:
        """層の四隅（上端を優先）に在庫箱を1個ずつ仮配置し、最上段になった場合でも
        四隅高さ揃えチェックを通過しやすくする。在庫が少ない最終層でも、
        連続した1行ではなく4隅individual配置になるためコーナー欠落を防げる。
        """
        # 上端(Y最大側)から埋めることで、行詰めが下から積み上がっても
        # 最終的に上端コーナーが空のまま残るリスクを減らす。
        corner_targets = [
            ("top", "left"), ("top", "right"),
            ("bottom", "left"), ("bottom", "right"),
        ]

        for cy_mode, cx_mode in corner_targets:
            candidates = sorted(
                (bid for bid, cnt in pool_counter.items() if cnt > 0),
                key=lambda bid: id_to_spec[bid].width * id_to_spec[bid].length,
                reverse=True
            )
            for bid in candidates:
                spec = id_to_spec[bid]
                placed_here = False
                for rot in (0, 90):
                    w, l = (spec.width, spec.length) if rot == 0 else (spec.length, spec.width)
                    x = 0.0 if cx_mode == "left" else max_row_width - w
                    y = 0.0 if cy_mode == "bottom" else max_total_depth - l
                    pb = self._try_place_at(x, y, spec, rot, layer_boxes, max_row_width, max_total_depth,
                                            base_z, layer_idx, lower_boxes)
                    if pb is not None:
                        layer_boxes.append(pb)
                        pool_counter[bid] -= 1
                        placed_here = True
                        break
                if placed_here:
                    break

    def _ep_fill_layer(self, layer_boxes: List[PlacedBox], pool_counter: Counter,
                       id_to_spec: Dict[str, BoxSpec], max_row_width: float, max_total_depth: float,
                       base_z: float, layer_idx: int, lower_boxes: List[PlacedBox]) -> None:
        """Extreme Points法によるフォールバック充填: 既配置箱の右端・下端＋原点を
        動的な候補位置とし、行詰めで埋まらなかった残渣を可能な限り充填する。
        """
        changed = True
        while changed:
            changed = False
            candidates = {(0.0, 0.0)}
            for pb in layer_boxes:
                candidates.add((round(pb.max_x, 2), round(pb.y, 2)))
                candidates.add((round(pb.x, 2), round(pb.max_y, 2)))
            sorted_candidates = sorted(candidates, key=lambda p: (p[1], p[0]))

            remaining_ids = sorted(
                (bid for bid, cnt in pool_counter.items() if cnt > 0),
                key=lambda bid: id_to_spec[bid].width * id_to_spec[bid].length,
                reverse=True
            )

            placed_this_round = False
            for bid in remaining_ids:
                spec = id_to_spec[bid]
                for (cx, cy) in sorted_candidates:
                    for rot in (0, 90):
                        pb = self._try_place_at(cx, cy, spec, rot, layer_boxes, max_row_width, max_total_depth,
                                                base_z, layer_idx, lower_boxes)
                        if pb is not None:
                            layer_boxes.append(pb)
                            pool_counter[bid] -= 1
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
        """1つの層（レイヤー）をMSP-EPハイブリッドでパッキングする。

        Phase A: 四隅アンカー配置（最上段の四隅高さ揃え要件を満たしやすくする）
        Phase B: Module-Aware Strip Packing（行分割 + 行内FFD詰め）
        Phase C: Extreme Points法による残渣充填
        """
        if not pool:
            return [], pool

        max_row_width = envelope["x_span"]
        max_total_depth = envelope["y_span"]

        pool_counter: Counter = Counter(b.id for b in pool)
        id_to_spec: Dict[str, BoxSpec] = {}
        for b in pool:
            id_to_spec.setdefault(b.id, b)

        # 上段の支持率判定に用いる「直下段」の箱リスト
        lower_boxes = [pb for pb in placed_so_far if pb.z < base_z - 1e-3] if layer_idx > 0 else []

        layer_boxes: List[PlacedBox] = []

        # Phase A: 四隅アンカー
        self._anchor_corners(layer_boxes, pool_counter, id_to_spec, max_row_width, max_total_depth,
                            base_z, layer_idx, lower_boxes)

        # Phase B: 行分割 + 行内FFD詰め（ボトムアップ）
        y_cursor = 0.0
        while y_cursor < max_total_depth - 1e-3:
            remaining_ids = [bid for bid, cnt in pool_counter.items() if cnt > 0]
            if not remaining_ids:
                break

            depth_budget = max_total_depth - y_cursor
            candidate_depths = sorted(
                {round(id_to_spec[bid].width, 1) for bid in remaining_ids if id_to_spec[bid].width <= depth_budget + 1.0} |
                {round(id_to_spec[bid].length, 1) for bid in remaining_ids if id_to_spec[bid].length <= depth_budget + 1.0},
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
            if counts_left.get(b.id, 0) > 0:
                remaining_pool.append(b)
                counts_left[b.id] -= 1

        for idx, pb in enumerate(layer_boxes, start=1):
            pb.order = idx

        return layer_boxes, remaining_pool

    def _align_pallet_bounds(self, placed_boxes: List[PlacedBox]):
        if not placed_boxes:
            return

        min_x = min(pb.x for pb in placed_boxes)
        max_x = max(pb.max_x for pb in placed_boxes)
        x_span = max_x - min_x

        min_y = min(pb.y for pb in placed_boxes)
        max_y = max(pb.max_y for pb in placed_boxes)
        y_span = max_y - min_y

        # 短辺センタリング
        if min_y < 0:
            shift_y = -min_y
            for pb in placed_boxes:
                pb.y = round(pb.y + shift_y, 2)
        elif max_y < self.pallet.max_y_span and y_span >= self.pallet.min_y_span:
            shift_y = (self.pallet.length - y_span) / 2.0 - min_y
            for pb in placed_boxes:
                pb.y = round(pb.y + shift_y, 2)

    # -------------------------------------------------------------------------
    # 3. 最高層四隅高さ揃え処理 (Top 4-Corner Leveling)
    # -------------------------------------------------------------------------
    def level_top_four_corners(self, placed_boxes: List[PlacedBox],
                               unplaced_boxes: List[Dict[str, Any]]) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        if not placed_boxes:
            return placed_boxes, unplaced_boxes

        min_x = min(pb.x for pb in placed_boxes)
        max_x = max(pb.max_x for pb in placed_boxes)
        min_y = min(pb.y for pb in placed_boxes)
        max_y = max(pb.max_y for pb in placed_boxes)

        margin = 35.0

        c1_boxes = [pb for pb in placed_boxes if pb.x <= min_x + margin and pb.y <= min_y + margin]
        c2_boxes = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.y <= min_y + margin]
        c3_boxes = [pb for pb in placed_boxes if pb.x <= min_x + margin and pb.max_y >= max_y - margin]
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

        if abs(max_corner_top - min_corner_top) <= 1.0 and abs(overall_top - max_corner_top) <= 1.0:
            return placed_boxes, unplaced_boxes

        target_level = min_corner_top
        leveled_boxes = []
        removed_count: Dict[str, int] = {}

        for pb in placed_boxes:
            if pb.top_z <= target_level + 1.0:
                leveled_boxes.append(pb)
            else:
                removed_count[pb.box_id] = removed_count.get(pb.box_id, 0) + 1

        unplaced_map = {item["box_id"]: item["count"] for item in unplaced_boxes}
        for bid, cnt in removed_count.items():
            unplaced_map[bid] = unplaced_map.get(bid, 0) + cnt

        new_unplaced = [{"box_id": k, "count": v} for k, v in unplaced_map.items() if v > 0]

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
                    if intersects_2d(pb.x, pb.y, pb.width, pb.length, other.x, other.y, other.width, other.length):
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

        min_x = min(pb.x for pb in placed_boxes)
        max_x = max(pb.max_x for pb in placed_boxes)
        x_span = max_x - min_x

        min_y = min(pb.y for pb in placed_boxes)
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
        if x_span >= self.pallet.max_x_span:
            violations.append(f"Long side span exceeded: {x_span:.1f}mm >= {self.pallet.max_x_span}mm")
        if y_span >= self.pallet.max_y_span:
            violations.append(f"Short side overhang exceeded: {y_span:.1f}mm >= {self.pallet.max_y_span}mm")
        if y_span < self.pallet.min_y_span - 1e-4:
            violations.append(f"Short side too small: {y_span:.1f}mm < {self.pallet.min_y_span}mm")

        # 四隅高さチェック
        margin = 35.0
        c1 = [pb for pb in placed_boxes if pb.x <= min_x + margin and pb.y <= min_y + margin]
        c2 = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.y <= min_y + margin]
        c3 = [pb for pb in placed_boxes if pb.x <= min_x + margin and pb.max_y >= max_y - margin]
        c4 = [pb for pb in placed_boxes if pb.max_x >= max_x - margin and pb.max_y >= max_y - margin]

        if c1 and c2 and c3 and c4:
            t1 = max(b.top_z for b in c1)
            t2 = max(b.top_z for b in c2)
            t3 = max(b.top_z for b in c3)
            t4 = max(b.top_z for b in c4)
            if not (abs(t1 - max_z) <= 1.0 and abs(t2 - max_z) <= 1.0 and abs(t3 - max_z) <= 1.0 and abs(t4 - max_z) <= 1.0):
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
