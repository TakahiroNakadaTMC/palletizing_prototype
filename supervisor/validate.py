#!/usr/bin/env python3
"""
独立制約バリデータ (validate.py)
constraints/constraints.md の全制約項目に基づき、
品番方式ランナーが生成した results-dir 配下の結果を独立・厳格に検証します。

v2026-11-03: 新パレット6項目 (length, width, height, max_x_span, max_y_span,
max_height) 方式に対応。下限(min800)・軸別オーバーハング上限(max_overhang_x_mm /
max_overhang_y_mm)・670mm例外・旧 max_small_edge_overhang_mm は廃止。
荷山の長辺/短辺/高さは各上限値「以下」であれば合格 (inclusive、下限なし)。
オーバーハングは合否に影響しない参考情報 (overhang_mm: left/right/front/back) として
算出するのみ。底面支持率85%判定は、パレット直置き分についても箱本体底面と
パレット矩形(原点〜length×width)との実交差面積で計算する。
本バリデータは algorithm_programmer の内部モデル・エンジンには依存せず、
独立した実装として制約を再計算する。
"""

import math
import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from constraints.top_support import TopSurface, evaluate_top_support, required_support_points

# 荷姿制約パラメータの既定値 (constraints/constraints.md より、PalletSpecの既定値と同一)
# パレットは6項目のみ: 物理寸法(length/width/height)と荷山上限(max_x_span/max_y_span/max_height)。
# いずれも0より大きい有限数値が必須。下限(旧min800)は存在しない。
PALLET_DIM_DEFAULTS: Dict[str, float] = {
    "length": 1200.0,       # mm (X軸 パレット物理長辺L)
    "width": 1000.0,        # mm (Y軸 パレット物理短辺W)
    "height": 130.0,        # mm (パレット本体の物理高さ。積載高には含めない)
    "max_x_span": 1360.0,   # mm (荷山長辺の上限、境界値を含む=inclusive、下限なし)
    "max_y_span": 1100.0,   # mm (荷山短辺の上限、境界値を含む=inclusive、下限なし)
    "max_height": 1200.0,   # mm (パレット上面からの積載高さ上限。固定キャップなし、設定値が常に正)
}
# 廃止されたキー。レガシー結果データに含まれていても無視する(エラーにしない/フォールバックしない=
# 単純に無視する)。新設定である6項目のみを使用する。
RETIRED_PALLET_KEYS = (
    "min_x_span", "min_y_span",
    "max_overhang_x_mm", "max_overhang_y_mm",
    "max_small_edge_overhang_mm",
)

# 底面支持率の下限(85%)。algorithm_programmer の engine 側判定(0.85 - 1e-6)に
# 合わせ、浮動小数点丸めで85.0%ちょうどが不合格側へ振れないよう同じ微小許容差を使う。
MIN_SUPPORT_RATIO = 0.85   # 底面支持面積比率の下限 (85%)
SUPPORT_RATIO_TOLERANCE = 1e-6
SUPPORT_CORNER_TOLERANCE_MM = 0.01
EPS = 1e-3                 # 浮動小数点誤差マージン
# 荷山スパン・高さの上限比較は、engine 側(1e-9)と揃えて僅かな丸め誤差のみ許容する。
SPAN_FLOAT_EPS = 1e-9
POSITION_REFERENCE = "combined_footprint_min_xy_top_z"

def get_footprint_bounds(box: Dict[str, Any]) -> Tuple[float, float, float, float]:
    pos = box["position"]
    dims = box["dimensions"]
    lid_dims = box.get("lid_dimensions", {})
    x, y = pos["x"], pos["y"]
    width, length = dims["width"], dims["length"]

    if box.get("lid_fit_type") in ("外嵌め", "内嵌め"):
        width = max(width, lid_dims.get("width", 0.0))
        length = max(length, lid_dims.get("length", 0.0))
        x -= (width - dims["width"]) / 2.0
        y -= (length - dims["length"]) / 2.0

    return x, y, x + width, y + length


def normalize_result_coordinates(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the current result coordinate reference to legacy internal coordinates."""
    if data.get("coordinate_reference") != POSITION_REFERENCE:
        return data

    normalized = dict(data)
    normalized_boxes = []
    for source_box in data.get("boxes", []):
        box = dict(source_box)
        position = dict(source_box["position"])
        dimensions = source_box["dimensions"]
        lid_dimensions = source_box.get("lid_dimensions", {})
        if box.get("lid_fit_type") in ("外嵌め", "内嵌め"):
            footprint_width = max(dimensions["width"], lid_dimensions.get("width", 0.0))
            footprint_length = max(dimensions["length"], lid_dimensions.get("length", 0.0))
        else:
            footprint_width = dimensions["width"]
            footprint_length = dimensions["length"]

        position["x"] += (footprint_width - dimensions["width"]) / 2.0
        position["y"] += (footprint_length - dimensions["length"]) / 2.0
        position["z"] -= dimensions["height"]
        box["position"] = position
        normalized_boxes.append(box)

    normalized["boxes"] = normalized_boxes
    return normalized

def intersects_2d_rect(x1, y1, w1, l1, x2, y2, w2, l2, eps=EPS):
    return not (x1 + w1 <= x2 + eps or x2 + w2 <= x1 + eps or
                y1 + l1 <= y2 + eps or y2 + l2 <= y1 + eps)

def get_intersection_area(x1, y1, w1, l1, x2, y2, w2, l2):
    ix_min = max(x1, x2)
    ix_max = min(x1 + w1, x2 + w2)
    iy_min = max(y1, y2)
    iy_max = min(y1 + l1, y2 + l2)
    if ix_max > ix_min and iy_max > iy_min:
        return (ix_max - ix_min) * (iy_max - iy_min)
    return 0.0

def covered_support_corners(
    upper: Dict[str, Any], supports: List[Dict[str, Any]]
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """本体底面が覆う下段外形の隅を集め、XY順の代表点で重複除外する。"""
    x, y = upper["position"]["x"], upper["position"]["y"]
    w, l = upper["dimensions"]["width"], upper["dimensions"]["length"]
    tolerance = SUPPORT_CORNER_TOLERANCE_MM + 1e-9
    covered: List[Tuple[float, float]] = []
    for lower in supports:
        x0, y0, x1, y1 = get_footprint_bounds(lower)
        for point in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            if (x - tolerance <= point[0] <= x + w + tolerance and
                y - tolerance <= point[1] <= y + l + tolerance):
                covered.append(point)
    unique = []
    for point in sorted(covered):
        if not any(abs(point[0] - other[0]) <= tolerance and
                   abs(point[1] - other[1]) <= tolerance for other in unique):
            unique.append(point)
    return covered, unique


def resolve_pallet_dims(pallet_data: Any, violations: List[str]) -> Dict[str, float]:
    """結果JSONの pallet 設定から新6項目を解決する。

    - 6項目 (length/width/height/max_x_span/max_y_span/max_height) は
      0より大きい有限数値であることを必須とする。欠落時のみ既定値を使う
      (これは正常な省略であり、無効値のフォールバックではない)。
      値が存在するのに無効(非数値・NaN・Inf・0以下・bool)な場合は、必ず
      明示的な違反として報告した上で、処理継続のために既定値へフォールバックする
      (値を無かったことにする「サイレント」なフォールバックではない)。
    - 旧キー(min_x_span/min_y_span/max_overhang_x_mm/max_overhang_y_mm/
      max_small_edge_overhang_mm)はレガシーデータとして単に無視する(エラーに
      しない)。
    - length/width は幅>長さの場合に入れ替える(既存どおりの正規化)。
    - max_y_span が max_x_span を上回る設定(短辺上限 > 長辺上限)は不正として報告する。
    """
    if not isinstance(pallet_data, dict):
        if pallet_data is not None:
            violations.append(
                "設定エラー: pallet はオブジェクト形式で指定してください。既定値を使用します"
            )
        pallet_data = {}

    resolved: Dict[str, float] = {}
    for name, default in PALLET_DIM_DEFAULTS.items():
        if name not in pallet_data:
            resolved[name] = default
            continue

        raw_value = pallet_data[name]
        value: Optional[float] = None
        try:
            if isinstance(raw_value, bool):
                raise ValueError("bool is not a dimension")
            value = float(raw_value)
        except (TypeError, ValueError):
            violations.append(
                f"設定エラー: pallet.{name} は0より大きい有限の数値で指定してください "
                f"({raw_value!r})。既定値 {default:g}mm を使用します"
            )
            resolved[name] = default
            continue

        if not math.isfinite(value) or value <= 0.0:
            violations.append(
                f"設定エラー: pallet.{name} は0より大きい有限の数値で指定してください "
                f"({value})。既定値 {default:g}mm を使用します"
            )
            resolved[name] = default
            continue

        resolved[name] = value

    length, width = resolved["length"], resolved["width"]
    if width > length:
        length, width = width, length
    resolved["length"], resolved["width"] = length, width

    if resolved["max_y_span"] > resolved["max_x_span"]:
        violations.append(
            "設定エラー: 荷山最大L (pallet.max_x_span="
            f"{resolved['max_x_span']:.1f}mm) は荷山最大W (pallet.max_y_span="
            f"{resolved['max_y_span']:.1f}mm) 以上にしてください"
        )

    # 旧キーはレガシーデータとして無視する(RETIRED_PALLET_KEYS は意図的に未参照)。
    return resolved


class PalletizeValidator:
    def __init__(self, box_db: Dict[str, Any], lid_db: Dict[str, Any],
                 catalog: Optional[Dict[str, Any]] = None, revision: Optional[str] = None,
                 pallet_db: Optional[Dict[str, Any]] = None):
        self.box_db = catalog["models"] if catalog is not None else box_db
        self.lid_db = catalog["lids"] if catalog is not None else lid_db
        self.catalog = catalog
        self.revision = revision
        self.pallet_db = pallet_db
        self.default_lid_id = next(
            (lid_id for lid_id, lid in self.lid_db.items() if lid.get("type") == "NONE"),
            "LID-010"
        )

    def _column_stack_group(self, box: Dict[str, Any]) -> Any:
        master = self.box_db.get(box.get("box_id"), {})
        lid_id = box.get("lid_id", self.default_lid_id)
        lid = self.lid_db.get(lid_id, {})
        if master.get("type") == "TP" and lid.get("fit_type") == "外嵌め":
            return "TP_EXTERNAL_LID", lid_id
        if master and master.get("type") != "TP":
            return "NON_TP", box.get("box_id")
        return None

    @staticmethod
    def _empty_report(test_name: str, violations: List[str], warnings: List[str],
                      physical_height: float = 0.0) -> Dict[str, Any]:
        return {
            "test_name": test_name,
            "is_pass": False,
            "total_boxes": 0,
            "x_span": 0.0,
            "y_span": 0.0,
            "max_z": 0.0,
            "vol_eff": 0.0,
            "physical_height": round(physical_height, 2),
            "total_height": round(physical_height, 2),
            "overhang_mm": {"left": 0.0, "right": 0.0, "front": 0.0, "back": 0.0},
            "violations": violations,
            "warnings": warnings,
            "top_support": evaluate_top_support([], 0.0, 0.0, 0.0, 0.0),
        }

    def validate_case(self, result_path: str) -> Dict[str, Any]:
        test_name = os.path.basename(result_path)
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            return self._empty_report(
                test_name, [f"結果ファイルの読み込みに失敗しました: {exc}"], []
            )

        if not isinstance(data, dict):
            return self._empty_report(
                test_name, ["結果データがオブジェクト形式ではありません"], []
            )
        data.setdefault("test_name", test_name)
        return self.validate_data(data)

    def validate_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """品番方式結果だけを受け付け、照合後に幾何検証を実行する。"""
        if data.get("input_mode") != "part_number" or data.get("schema_version") != 2:
            return self._empty_report(
                data.get("test_name", "unknown"),
                ["旧方式の結果入力は廃止されました。part_number方式の結果を指定してください"],
                [],
            )
        from supervisor.catalog_validation import resolve_catalog_result
        try:
            resolved, part_counts = resolve_catalog_result(
                data, self.catalog, self.revision, self.pallet_db)
            identity_valid = True
            report = self._validate_geometry(resolved)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            report = self._empty_report(
                data.get("test_name", "unknown"), ["品番結果の検証エラー: " + str(error)], [])
            part_counts = []
            identity_valid = False
        report.update(input_mode="part_number", part_counts=part_counts,
                      identity_valid=identity_valid,
                      catalog_revision=data.get("catalog_revision"),
                      unplaced_boxes=data.get("unplaced_boxes") if identity_valid else [],
                      input_boxes_count=data.get("input_boxes_count") if identity_valid else None,
                      unplaced_boxes_count=data.get("unplaced_boxes_count") if identity_valid else None)
        if part_counts:
            identities = {box["order"]: box for box in data["boxes"]}
            for field in ("support_boxes", "multi_corner_boxes"):
                for item in report["top_support"].get(field, []):
                    source = identities[item["order"]]
                    item.update({key: source[key] for key in (
                        "box_id", "part_number", "supplier_name", "box_name", "box_model_id", "lid_id")})
        return report

    def validate_geometry_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """品番照合を行わず、幾何制約のみ独立検証するテスト用ヘルパー。"""
        return self._validate_geometry(data)

    def _validate_geometry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        data = normalize_result_coordinates(data)
        test_name = data.get("test_name", "unknown")

        violations: List[str] = []
        warnings: List[str] = []

        # -------------------------------------------------------------
        # 0. パレット設定(新6項目)の検証。箱が0件の場合でも必ず実行する。
        # -------------------------------------------------------------
        pallet = resolve_pallet_dims(data.get("pallet"), violations)
        pallet_x_length = pallet["length"]
        pallet_y_width = pallet["width"]
        physical_height = pallet["height"]
        max_height = pallet["max_height"]
        max_x_span = pallet["max_x_span"]
        max_y_span = pallet["max_y_span"]

        boxes = data.get("boxes", [])
        if not isinstance(boxes, list):
            violations.append("結果データのboxesがリスト形式ではありません")
            boxes = []
        total_boxes = len(boxes)

        if total_boxes == 0:
            violations.append("配置箱数が0です")
            return self._empty_report(test_name, violations, warnings, physical_height)

        # -------------------------------------------------------------
        # 1. 荷姿寸法・境界制約の検証 (inclusive、下限なし)
        # -------------------------------------------------------------
        footprint_bounds = [get_footprint_bounds(b) for b in boxes]
        min_x = min(bounds[0] for bounds in footprint_bounds)
        max_x = max(bounds[2] for bounds in footprint_bounds)
        x_span = max_x - min_x

        min_y = min(bounds[1] for bounds in footprint_bounds)
        max_y = max(bounds[3] for bounds in footprint_bounds)
        y_span = max_y - min_y

        max_z = max(b["position"]["z"] + b["dimensions"]["height"] for b in boxes)

        # (1) 最大積載高 (ケースごとの pallet.max_height が常に権威値。固定1200キャップは無い)
        if max_z > max_height + SPAN_FLOAT_EPS:
            violations.append(
                f"最大積載高さ超過: {max_z:.1f}mm > {max_height:.1f}mm "
                f"(上限は{max_height:.1f}mm以下、超過: {max_z - max_height:.1f}mm)"
            )

        # (2) 長辺荷姿スパン (0 < X <= max_x_span。下限(旧800mm)は廃止、上限は境界値を含む)
        if x_span > max_x_span + SPAN_FLOAT_EPS:
            violations.append(
                f"長辺荷姿スパン超過: {x_span:.1f}mm > {max_x_span:.1f}mm "
                f"(上限は{max_x_span:.1f}mm以下、下限なし)"
            )

        # (3) 短辺荷姿スパン (0 < Y <= max_y_span。下限(旧800mm)は廃止、上限は境界値を含む)
        if y_span > max_y_span + SPAN_FLOAT_EPS:
            violations.append(
                f"短辺荷姿スパン超過: {y_span:.1f}mm > {max_y_span:.1f}mm "
                f"(上限は{max_y_span:.1f}mm以下、下限なし)"
            )

        # (4) 荷姿センタリング (中心座標誤差0.01mm以内)
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        if (abs(center_x - pallet_x_length / 2.0) > 0.01 or
            abs(center_y - pallet_y_width / 2.0) > 0.01):
            violations.append(
                f"荷姿センタリング違反: 中心 ({center_x:.2f}, {center_y:.2f})mm, "
                f"パレット中心 ({pallet_x_length / 2.0:.2f}, {pallet_y_width / 2.0:.2f})mm"
            )

        # (5) オーバーハング(パレット端はみ出し)は合否に影響しない参考情報として算出する。
        #     箱・蓋の結合外形全体のバウンディングボックスを用いる。
        overhang = {
            "left": round(max(0.0, -min_x), 2),
            "right": round(max(0.0, max_x - pallet_x_length), 2),
            "front": round(max(0.0, -min_y), 2),
            "back": round(max(0.0, max_y - pallet_y_width), 2),
        }
        if any(value > 0 for value in overhang.values()):
            warnings.append(
                "要確認: パレットからのはみ出し "
                f"左{overhang['left']} / 右{overhang['right']} / "
                f"手前{overhang['front']} / 奥{overhang['back']}mm（合否とは別の確認情報）"
            )

        # -------------------------------------------------------------
        # 2. 各箱の幾何・回転・天地固定・嵌合寸法の検証
        # -------------------------------------------------------------
        for b in boxes:
            bid = b["box_id"]
            order = b["order"]
            pos = b["position"]
            dims = b["dimensions"]
            rot = b["rotation"]

            if bid not in self.box_db:
                violations.append(f"Order #{order}: 未知の箱型番 '{bid}' が使用されています")
                continue

            master = self.box_db[bid]
            lid_id = b.get("lid_id", self.default_lid_id)
            lid_thickness = float(b.get("lid_thickness", 0.0))
            lid = self.lid_db.get(lid_id)
            if lid is None:
                violations.append(f"Order #{order} ({bid}): 未知の蓋ID '{lid_id}' が使用されています")
            else:
                compatible_lids = master.get("compatible_lids", [])
                if lid.get("type") != "NONE" and compatible_lids and lid_id not in compatible_lids:
                    violations.append(f"Order #{order} ({bid}): 蓋 '{lid_id}' は箱と互換性がありません")
                if b.get("lid_fit_type", "なし") != lid.get("fit_type", "なし"):
                    violations.append(f"Order #{order} ({bid}): 蓋の嵌め方が蓋DBと一致しません")
                if abs(lid_thickness - float(lid.get("thickness", 0.0))) > EPS:
                    violations.append(f"Order #{order} ({bid}): 蓋厚データが蓋DBと一致しません")
                output_lid_dims = b.get("lid_dimensions", {})
                expected_lid_width = float(lid.get("length" if rot == 90 else "width", 0.0))
                expected_lid_length = float(lid.get("width" if rot == 90 else "length", 0.0))
                if (abs(float(output_lid_dims.get("width", 0.0)) - expected_lid_width) > EPS or
                        abs(float(output_lid_dims.get("length", 0.0)) - expected_lid_length) > EPS):
                    violations.append(f"Order #{order} ({bid}): 蓋寸法が蓋DBと一致しません")

            # 天地固定（高さチェック）
            expected_height = float(master["height"]) + lid_thickness
            if abs(dims["height"] - expected_height) > EPS:
                violations.append(f"Order #{order} ({bid}): 高さ不一致（箱高+蓋厚 {expected_height}mm に対して {dims['height']}mm）")

            # 回転角チェック
            if rot not in [0, 90]:
                violations.append(f"Order #{order} ({bid}): 不正な回転角 {rot}° (0°または90°のみ許可)")

            # 水平寸法チェック
            if rot == 0:
                if abs(dims["width"] - master["width"]) > EPS or abs(dims["length"] - master["length"]) > EPS:
                    violations.append(f"Order #{order} ({bid}): 0度回転時の寸法不一致")
            elif rot == 90:
                if abs(dims["width"] - master["length"]) > EPS or abs(dims["length"] - master["width"]) > EPS:
                    violations.append(f"Order #{order} ({bid}): 90度回転時の寸法不一致")

        # -------------------------------------------------------------
        # 3. 3D干渉（衝突）＆ 嵌合深さ沈み込みの検証
        # -------------------------------------------------------------
        for i in range(total_boxes):
            b1 = boxes[i]
            for j in range(i + 1, total_boxes):
                b2 = boxes[j]

                # 2D平面での重なりチェック
                b1_bounds = get_footprint_bounds(b1)
                b2_bounds = get_footprint_bounds(b2)
                if intersects_2d_rect(b1_bounds[0], b1_bounds[1], b1_bounds[2] - b1_bounds[0], b1_bounds[3] - b1_bounds[1],
                                      b2_bounds[0], b2_bounds[1], b2_bounds[2] - b2_bounds[0], b2_bounds[3] - b2_bounds[1]):

                    b1_z = b1["position"]["z"]
                    b1_top = b1_z + b1["dimensions"]["height"]
                    b2_z = b2["position"]["z"]
                    b2_top = b2_z + b2["dimensions"]["height"]

                    # b2がb1の上に載る場合: b2_z >= b1_top - b2.fitting_depth
                    if b2_z >= b1_top - b2["fitting_depth"] - EPS:
                        continue
                    # b1がb2の上に載る場合: b1_z >= b2_top - b1.fitting_depth
                    if b1_z >= b2_top - b1["fitting_depth"] - EPS:
                        continue

                    # Z区間が重なる場合は不正な食い込み衝突
                    if not (b1_top <= b2_z + EPS or b2_top <= b1_z + EPS):
                        violations.append(f"3D幾何衝突: Order #{b1['order']} ({b1['box_id']}) と Order #{b2['order']} ({b2['box_id']}) が空間干渉しています")

        # -------------------------------------------------------------
        # 4. 空中浮き防止 ＆ 底面支持面積比率の検証
        #    (パレット直置き分についても、箱本体底面とパレット矩形
        #     (原点0,0 〜 pallet_x_length,pallet_y_width) との実交差面積を
        #     支持面積に算入する。蓋の張り出しは支持面に含めない)
        # -------------------------------------------------------------
        for b in boxes:
            order = b["order"]
            z = b["position"]["z"]
            x = b["position"]["x"]
            y = b["position"]["y"]
            w = b["dimensions"]["width"]
            l = b["dimensions"]["length"]
            fitting = b["fitting_depth"]

            is_on_pallet = z <= EPS
            pallet_support_area = 0.0
            if is_on_pallet:
                pallet_support_area = get_intersection_area(
                    x, y, w, l, 0.0, 0.0, pallet_x_length, pallet_y_width
                )

            # 直下にある下段箱を探索 (パレット直置きの場合も、他の箱が同じZ帯に
            # 存在する可能性はゼロではないため、通常通り探索する)
            supporting_boxes = []
            for other in boxes:
                if other["order"] == order:
                    continue
                other_top = other["position"]["z"] + other["dimensions"]["height"]
                # 上面Zが (z + fitting) と一致しているか
                if abs(other_top - (z + fitting)) <= 1.0:
                    other_bounds = get_footprint_bounds(other)
                    if intersects_2d_rect(x, y, w, l, other_bounds[0], other_bounds[1],
                                          other_bounds[2] - other_bounds[0], other_bounds[3] - other_bounds[1]):
                        supporting_boxes.append(other)

            if not supporting_boxes and pallet_support_area <= 0.0:
                violations.append(f"Order #{order} ({b['box_id']}): 空中浮遊エラー（パレットまたは下段に支持する箱が存在しません）")
                continue

            if data.get("input_mode") == "part_number":
                upper_bounds = get_footprint_bounds(b)
                actual_support = []
                if not is_on_pallet:
                    for other in boxes:
                        lower_bounds = get_footprint_bounds(other)
                        if (other["order"] < order
                                and abs(other["position"]["z"] + other["dimensions"]["height"] - (z + fitting)) <= 1.0
                                and intersects_2d_rect(
                                    upper_bounds[0], upper_bounds[1],
                                    upper_bounds[2] - upper_bounds[0], upper_bounds[3] - upper_bounds[1],
                                    lower_bounds[0], lower_bounds[1],
                                    lower_bounds[2] - lower_bounds[0], lower_bounds[3] - lower_bounds[1])):
                            actual_support.append(other["order"])
                if sorted(b["supported_by"]) != actual_support:
                    violations.append(f"Order #{order}: 下段支持番号が配置座標と一致しません")

            if not is_on_pallet:
                upper_group = self._column_stack_group(b)
                lower_column_boxes = [
                    sb for sb in supporting_boxes
                    if self._column_stack_group(sb) is not None
                ]
                aligned_column_supports = [
                    sb for sb in supporting_boxes
                    if self._column_stack_group(sb) == upper_group
                    and all(abs(a - c) <= 0.01 for a, c in zip(get_footprint_bounds(sb), get_footprint_bounds(b)))
                ]
                column_rule_failed = (
                    (upper_group is None and bool(lower_column_boxes))
                    or (upper_group is not None and
                        (len(supporting_boxes) != 1 or len(aligned_column_supports) != 1))
                )
                if column_rule_failed:
                    violations.append(
                        f"Order #{order} ({b['box_id']}): コラム積み条件違反 "
                        "（対象群・蓋ID・箱蓋外形位置を揃えた単一支持が必要です）"
                    )

                # v2026-10-27: 適合コラム積みだけ免除し、下段隅を位置で集計する。
                if upper_group is None or column_rule_failed:
                    covered, unique = covered_support_corners(b, supporting_boxes)
                    if len(unique) < 2:
                        violations.append(
                            f"Order #{order} ({b['box_id']}): 下段隅の被覆不足 "
                            f"(支持箱={[sb['order'] for sb in supporting_boxes]}, "
                            f"被覆隅={covered}, 重複除外前={len(covered)}, "
                            f"重複除外後={len(unique)} < 2, 位置={unique})"
                        )

            # 支持面積比率の算出 (パレット直置き面積 + 下段箱との重なり面積)
            total_support_area = pallet_support_area
            for sb in supporting_boxes:
                sb_bounds = get_footprint_bounds(sb)
                area = get_intersection_area(x, y, w, l, sb_bounds[0], sb_bounds[1],
                                             sb_bounds[2] - sb_bounds[0], sb_bounds[3] - sb_bounds[1])
                total_support_area += area

            box_bottom_area = w * l
            support_ratio = total_support_area / box_bottom_area if box_bottom_area > 0 else 0.0
            if support_ratio < MIN_SUPPORT_RATIO - SUPPORT_RATIO_TOLERANCE:
                violations.append(f"Order #{order} ({b['box_id']}): 支持面積不足 ({support_ratio*100:.1f}% < {MIN_SUPPORT_RATIO*100:.0f}%)")

            # 下段箱が上段箱より幅・奥行き両方とも大きい場合はNG
            # （上段箱が下段箱の縁からずれた不安定な段積みとなり荷崩れの危険があるため）
            for sb in supporting_boxes:
                sb_w = sb["dimensions"]["width"]
                sb_l = sb["dimensions"]["length"]
                if sb_w > w + 1.0 and sb_l > l + 1.0:
                    violations.append(
                        f"Order #{order} ({b['box_id']}): 下段箱サイズ超過エラー "
                        f"(下段 Order #{sb['order']} ({sb['box_id']}) {sb_w:.0f}x{sb_l:.0f}mm が "
                        f"上段 {w:.0f}x{l:.0f}mm より大きいため段積み不可)"
                    )

        # -------------------------------------------------------------
        # 5. 積み込み順序（Order）のトポロジカル依存性検証
        # -------------------------------------------------------------
        for b in boxes:
            order = b["order"]
            z = b["position"]["z"]
            fitting = b["fitting_depth"]

            if z <= EPS:
                continue

            for other in boxes:
                if other["order"] == order:
                    continue
                other_top = other["position"]["z"] + other["dimensions"]["height"]
                if abs(other_top - (z + fitting)) <= 1.0:
                    upper_bounds = get_footprint_bounds(b)
                    lower_bounds = get_footprint_bounds(other)
                    if intersects_2d_rect(upper_bounds[0], upper_bounds[1], upper_bounds[2] - upper_bounds[0], upper_bounds[3] - upper_bounds[1],
                                          lower_bounds[0], lower_bounds[1], lower_bounds[2] - lower_bounds[0], lower_bounds[3] - lower_bounds[1]):
                        if other["order"] >= order:
                            violations.append(f"積み順トポロジカル違反: 上段 Order #{order} ({b['box_id']}) が下段 Order #{other['order']} ({other['box_id']}) より先に配置されています")

        # -------------------------------------------------------------
        # 6. v2026-11-05: 出力座標から上載せ平パレットの接触支持を再計算
        # -------------------------------------------------------------
        surfaces = []
        for box, bounds in zip(boxes, footprint_bounds):
            box_id = box["box_id"]
            try:
                points = required_support_points(box_id, self.box_db.get(box_id, {}))
            except ValueError as exc:
                violations.append(str(exc))
                continue
            bottom = box["position"]["z"]
            surfaces.append(TopSurface(box["order"], box_id, bounds, bottom,
                                       bottom + box["dimensions"]["height"], points))
        top_support = evaluate_top_support(surfaces, pallet_x_length, pallet_y_width,
                                           max_x_span, max_y_span)
        violations.extend(top_support["violations"])

        is_pass = (len(violations) == 0)

        pallet_vol = pallet_x_length * pallet_y_width * max_height
        box_vol = sum(b["dimensions"]["width"] * b["dimensions"]["length"] * b["dimensions"]["height"] for b in boxes)
        vol_eff = (box_vol / pallet_vol) * 100.0 if pallet_vol > 0 else 0.0

        return {
            "test_name": test_name,
            "is_pass": is_pass,
            "total_boxes": total_boxes,
            "x_span": x_span,
            "y_span": y_span,
            "max_z": max_z,
            "vol_eff": vol_eff,
            "physical_height": round(physical_height, 2),
            "total_height": round(physical_height + max_z, 2),
            "overhang_mm": overhang,
            "violations": violations,
            "warnings": warnings,
            "top_support": top_support
        }

def _default_report_dir(results_dir: Path) -> Path:
    return Path(PROJECT_ROOT) / "supervisor" / "catalog_reports" / results_dir.resolve().name

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="荷姿制約の独立検証")
    parser.add_argument("--results-dir", type=Path, help="品番方式の一括結果フォルダ")
    parser.add_argument("--catalog-results", dest="results_dir_alias", type=Path,
                        help="--results-dir の旧エイリアス")
    parser.add_argument("--report-dir", type=Path, help="検証レポート出力フォルダ")
    args = parser.parse_args()
    if args.results_dir is not None and args.results_dir_alias is not None:
        parser.error("--results-dir と --catalog-results は同時に指定できません")
    results_dir = args.results_dir or args.results_dir_alias
    if results_dir is None:
        parser.error("--results-dir を指定してください")
    report_dir = args.report_dir or _default_report_dir(results_dir)
    from supervisor.catalog_validation import validate_catalog_run
    try:
        sys.exit(validate_catalog_run(Path(PROJECT_ROOT), results_dir, report_dir))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, "品番方式の独立検証エラー: {}\n".format(error))
