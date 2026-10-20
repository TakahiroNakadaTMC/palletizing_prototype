"""Stage 1: editable L-hand geometry only; no placement feasibility judgement."""

import math
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from algorithm_programmer.models import BoxSpec


CORNERS = ("X_MIN_Y_MIN", "X_MAX_Y_MIN", "X_MAX_Y_MAX", "X_MIN_Y_MAX")
PARAMETERS = {
    "body_u_length": (700.0, True),
    "body_v_length": (700.0, True),
    "body_thickness": (20.0, True),
    "body_height": (40.0, True),
    "body_bottom": (20.0, False),
    "finger_length": (40.0, True),
    "finger_thickness": (12.0, True),
    "finger_depth": (30.0, True),
    "u_end_distance": (50.0, False),
    "v_end_distance": (50.0, False),
    "clearance": (2.0, False),
}
SIGNED = {"body_bottom"}


class HandGeometryRangeError(ValueError):
    """The equipment geometry does not support this box/corner."""


def sample_profile() -> Dict[str, Any]:
    """Return illustrative dimensions, not measured equipment specifications."""
    return {
        "id": "sample-l-hand",
        "name": "サンプルL字ハンド（仮寸法・実機未検証）",
        "parameters": {key: value for key, (value, _) in PARAMETERS.items()},
    }


def number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{}: 数値を指定してください".format(label))
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError("{}: 数値が大きすぎます".format(label)) from error
    if not math.isfinite(result):
        raise ValueError("{}: 有限の数値を指定してください".format(label))
    return result


def validate_profile(profile: Any) -> None:
    if not isinstance(profile, dict):
        raise ValueError("ハンド設定はオブジェクトで指定してください")
    if set(profile) != {"id", "name", "parameters"}:
        raise ValueError("ハンド設定の項目が不足、または未対応の項目があります")
    for key in ("id", "name"):
        if not isinstance(profile[key], str) or not profile[key].strip():
            raise ValueError("{}: 空でない文字列を指定してください".format(key))
    parameters = profile["parameters"]
    if not isinstance(parameters, dict) or set(parameters) != set(PARAMETERS):
        raise ValueError("設備共通の形状パラメータの項目が一致しません")
    for key, (_, positive) in PARAMETERS.items():
        value = number(parameters[key], key)
        if (positive and value <= 0) or (not positive and key not in SIGNED and value < 0):
            raise ValueError("{}: 範囲外です".format(key))
    if parameters["body_bottom"] + parameters["body_height"] <= -parameters["finger_depth"]:
        raise ValueError("本体上面は爪の下端より高くしてください")


def validate_store(data: Any) -> None:
    if (not isinstance(data, dict) or set(data) != {"schema_version", "profiles"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or not isinstance(data["profiles"], list) or not data["profiles"]):
        raise ValueError("schema_version=1 と1件以上の profiles が必要です")
    ids = []
    for profile in data["profiles"]:
        validate_profile(profile)
        ids.append(profile["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("設備IDが重複しています")


def load_profile(path: Optional[str] = None, profile_id: Optional[str] = None) -> Dict[str, Any]:
    """Load the sole equipment profile, or explicitly select an equipment ID."""
    source = Path(path) if path is not None else Path(__file__).with_name("hand_profiles.json")
    with source.open(encoding="utf-8") as stream:
        store = json.load(stream)
    validate_store(store)
    profiles = store["profiles"]
    if profile_id is None:
        if len(profiles) != 1:
            raise ValueError("設備設定が複数あります。使用するハンドの設備IDを指定してください")
        return profiles[0]
    for profile in profiles:
        if profile["id"] == profile_id:
            return profile
    raise ValueError("ハンドの設備IDが見つかりません: {}".format(profile_id))


def build_preview(profile: Dict[str, Any], box: BoxSpec, rotation: int,
                  corner: str) -> Dict[str, Any]:
    """Build cuboids in pallet axes, relative to the combined minimum XY/top Z.

    Box-local X/Y follow the engine's rotation-zero convention: DB W/L.
    Hand U/V rotate rigidly at each corner; they are never mirrored.
    """
    validate_profile(profile)
    if type(rotation) is not int or rotation not in (0, 90):
        raise ValueError("箱の回転は0°または90°を指定してください")
    if corner not in CORNERS:
        raise ValueError("確認する把持角を指定してください")
    sx = number(box.footprint_width, "箱・蓋のX寸法")
    sy = number(box.footprint_length, "箱・蓋のY寸法")
    height = number(box.height + box.lid_thickness, "蓋込み高さ")
    if min(sx, sy, height) <= 0:
        raise ValueError("箱・蓋寸法は正数にしてください")
    p = profile["parameters"]
    index = CORNERS.index(corner)
    anchors = ((0, 0), (sx, 0), (sx, sy), (0, sy))
    ax, ay = anchors[index]
    span_u, span_v = (sx, sy) if index % 2 == 0 else (sy, sx)
    for axis, span in (("u", span_u), ("v", span_v)):
        distance = p[axis + "_end_distance"]
        half = p["finger_length"] / 2
        if distance < half or distance + half > span:
            raise HandGeometryRangeError("{}爪が辺からはみ出します。端からの距離または爪長を調整してください".format(axis.upper()))
        if span - distance + half > p["body_" + axis + "_length"]:
            raise HandGeometryRangeError("{}爪が本体の長さを超えます。この箱・把持角は設定範囲外です".format(axis.upper()))
    turn = index
    cosines = (1, 0, -1, 0)
    sines = (0, 1, 0, -1)

    def point(u: float, v: float, z: float) -> List[float]:
        x = ax + cosines[turn] * u - sines[turn] * v
        y = ay + sines[turn] * u + cosines[turn] * v
        if rotation == 90:
            x, y = sy - y, x
        return [x, y, z]

    def cuboid(name: str, low: List[float], high: List[float]) -> Dict[str, Any]:
        points = [point(u, v, z) for u in (low[0], high[0])
                  for v in (low[1], high[1]) for z in (low[2], high[2])]
        return {
            "name": name,
            "min": [min(pt[i] for pt in points) for i in range(3)],
            "max": [max(pt[i] for pt in points) for i in range(3)],
        }

    thickness, bottom = p["body_thickness"], p["body_bottom"]
    bodies = [
        cuboid("U側本体", [0, -thickness, bottom],
               [p["body_u_length"], 0, bottom + p["body_height"]]),
        cuboid("V側本体", [-thickness, 0, bottom],
               [0, p["body_v_length"], bottom + p["body_height"]]),
    ]
    half, ft, depth = p["finger_length"] / 2, p["finger_thickness"], p["finger_depth"]
    u, v = span_u - p["u_end_distance"], span_v - p["v_end_distance"]

    fingers = [
        cuboid("U辺の爪の干渉範囲", [u - half, -ft, -depth],
               [u + half, 0, bottom + p["body_height"]]),
        cuboid("V辺の爪の干渉範囲", [-ft, v - half, -depth],
               [0, v + half, bottom + p["body_height"]]),
    ]
    origin = point(0, 0, 0)
    return {
        "coordinate_reference": "combined_footprint_min_xy_top_z",
        "box_size": [sy, sx, height] if rotation else [sx, sy, height],
        "corner_id": corner,
        "reference_position": origin,
        "hand_yaw_deg": (index * 90 + rotation) % 360,
        "axes": {"u": point(80, 0, 0), "v": point(0, 80, 0)},
        "envelope": bodies + fingers,
        "clearance": p["clearance"],
        "feasibility_checked": False,
    }
