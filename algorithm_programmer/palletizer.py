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
    # -------------------------------------------------------------------------
    def palletize_mixed(self, boxes: List[BoxSpec]) -> Tuple[List[PlacedBox], List[Dict[str, Any]]]:
        """混載パレタイズ: レイヤー別パッキングと四隅高さ揃え"""
        placed_boxes: List[PlacedBox] = []

        # 箱をフットプリントと高さで整理
        # TPモジュールグリッド (335mm単位)
        # 1200x1000 パレットに対して 1340mm (4 x 335) x 1005mm (3 x 335) の6スロット (2x3 または 4x3)
        # スロットグリッド: X=0, 335, 670, 1005 (幅1340mm), Y=0, 335, 670 (奥行1005mm)
        slots_2x3 = [
            # 670x503 箱用、または 670x335, 335x335 の組み合わせ
            # 2列 x 2行 (670x503) = 1340 x 1006
            # 2列 x 3行 (670x335) = 1340 x 1005
            # 4列 x 3行 (335x335) = 1340 x 1005
        ]

        # 利用可能な箱のプール
        box_pool = list(boxes)
        box_pool.sort(key=lambda b: (b.width * b.length, b.height), reverse=True)

        current_z = 0.0
        current_fitting = 8.0

        # パレット上面または前層の上面から、層ごとに積み上げる
        layer_idx = 0
        while box_pool and current_z < self.pallet.max_height:
            layer_placed, remaining_pool = self._pack_mixed_layer(box_pool, current_z, layer_idx)
            if not layer_placed:
                break

            # この層の最高上面
            layer_top = max(pb.top_z for pb in layer_placed)
            if layer_top > self.pallet.max_height + 1e-4:
                break

            # この層で四隅が揃っているか確認
            min_x = min(pb.x for pb in layer_placed)
            max_x = max(pb.max_x for pb in layer_placed)
            min_y = min(pb.y for pb in layer_placed)
            max_y = max(pb.max_y for pb in layer_placed)
            margin = 35.0

            c1 = any(pb.x <= min_x + margin and pb.y <= min_y + margin for pb in layer_placed)
            c2 = any(pb.max_x >= max_x - margin and pb.y <= min_y + margin for pb in layer_placed)
            c3 = any(pb.x <= min_x + margin and pb.max_y >= max_y - margin for pb in layer_placed)
            c4 = any(pb.max_x >= max_x - margin and pb.max_y >= max_y - margin for pb in layer_placed)

            if not (c1 and c2 and c3 and c4) and layer_idx > 0:
                # 四隅が揃わない中途半端な層は積まない
                break

            placed_boxes.extend(layer_placed)
            box_pool = remaining_pool
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

    def _pack_mixed_layer(self, pool: List[BoxSpec], base_z: float, layer_idx: int) -> Tuple[List[PlacedBox], List[BoxSpec]]:
        """1つの層（レイヤー）を2Dモジュールグリッドで隙間なくパッキング"""
        placed: List[PlacedBox] = []
        rem_pool = list(pool)

        # ターゲット荷姿: 1340 x 1005 (または 1006)
        # パレット中心へのセンタリングオフセット
        offset_x = (self.pallet.width - 1340.0) / 2.0  # -70.0 (パレット上では 0〜1340)
        offset_y = (self.pallet.length - 1005.0) / 2.0  # -2.5 (パレット上では 0〜1005)
        if offset_x < 0: offset_x = (1360.0 - 1340.0) / 2.0  # 10.0
        if offset_y < 0: offset_y = 0.0

        # モジュールグリッド定義: 4列 (X: 0, 335, 670, 1005) x 3行 (Y: 0, 335, 670) または 2行 (Y: 0, 503)
        # スロットマトリクス (4x6 の 335x168 サブセル等)
        occupied = [[False for _ in range(6)] for _ in range(4)]  # 4x6 グリッド (dx=335, dy=168)

        # 箱の選択と配置
        # 四隅を確実に埋める順序: (0,0), (3,0), (0,4), (3,4), その他内部
        corners_order = [
            (0, 0), (2, 0), (0, 3), (2, 3),
            (1, 0), (1, 3), (0, 1), (2, 1), (1, 1), (0, 2), (2, 2), (1, 2)
        ]

        # プール内の代表的な箱の高さをこの層の標準高さとする
        first_box = rem_pool[0]
        layer_h = first_box.height

        # この層に適した高さの箱を優先配置
        suitable_boxes = [b for b in rem_pool if abs(b.height - layer_h) <= 1.0]
        other_boxes = [b for b in rem_pool if abs(b.height - layer_h) > 1.0]

        curr_pool = suitable_boxes + other_boxes
        rem_pool = []

        # グリッド配置
        # 1340 x 1005 をカバーするブロック配置
        grid_x_steps = [0.0, 335.0, 670.0, 1005.0]
        grid_y_steps = [0.0, 335.0, 670.0]

        # 670x503 の場合は 2x2
        # まず大きい箱（TP-462: 670x503, TP-362: 670x335）を配置できるか試す
        for b in curr_pool:
            placed_box = False
            # 0度と90度を試す
            for rot in [0, 90]:
                bw, bl = (b.width, b.length) if rot == 0 else (b.length, b.width)

                # パレット許容枠チェック
                for gx in [0.0, 335.0, 670.0, 1005.0]:
                    for gy in [0.0, 335.0, 503.0, 670.0]:
                        if gx + bw > 1341.0 or gy + bl > 1008.0:
                            continue

                        # 既存配置との重なりチェック
                        overlap = False
                        for pb in placed:
                            if intersects_2d(gx, gy, bw, bl, pb.x, pb.y, pb.width, pb.length):
                                overlap = True
                                break

                        if not overlap:
                            pb = PlacedBox(
                                order=len(placed) + 1,
                                box_id=b.id,
                                x=round(gx, 2),
                                y=round(gy, 2),
                                z=round(base_z, 2),
                                width=bw,
                                length=bl,
                                height=b.height,
                                fitting_depth=b.fitting_depth,
                                rib_thickness=b.rib_thickness,
                                rotation=rot,
                                layer_index=layer_idx
                            )
                            placed.append(pb)
                            placed_box = True
                            break
                    if placed_box:
                        break
            if not placed_box:
                rem_pool.append(b)

        # もし1箱も置けなかったら終了
        if not placed:
            return [], pool

        return placed, rem_pool

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
