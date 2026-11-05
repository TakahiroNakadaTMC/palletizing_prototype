"""
パレタイズデータモデル定義 (models.py)
"""

import math
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from constraints.top_support import required_support_points

POSITION_REFERENCE = "combined_footprint_min_xy_top_z"

@dataclass
class BoxSpec:
    id: str
    name: str
    type: str                     # "TP" or "NON_TP"
    width: float                  # mm (箱DB上の短手方向 W)
    length: float                 # mm (箱DB上の長手方向 L)
    height: float                 # mm (外寸高さ)
    fitting_depth: float          # mm (嵌合沈み込み深さ)
    rib_thickness: float          # mm (側面リブ厚み)
    module_ratio: Optional[str] = None  # "1x1", "1.5x1", "2x1", etc.
    description: str = ""
    lid_id: str = ""
    lid_width: float = 0.0
    lid_length: float = 0.0
    lid_thickness: float = 0.0
    lid_fit_type: str = "なし"
    top_support_points: Optional[int] = None

    def __post_init__(self) -> None:
        self.top_support_points = self.required_top_support_points

    @property
    def required_top_support_points(self) -> int:
        record = {} if self.top_support_points is None else {"top_support_points": self.top_support_points}
        return required_support_points(self.id, record)

    @property
    def pool_key(self) -> Tuple[str, str]:
        return self.id, self.lid_id

    @property
    def footprint_width(self) -> float:
        if self.lid_fit_type in ("外嵌め", "内嵌め"):
            return max(self.width, self.lid_width)
        return self.width

    @property
    def footprint_length(self) -> float:
        if self.lid_fit_type in ("外嵌め", "内嵌め"):
            return max(self.length, self.lid_length)
        return self.length

    @property
    def is_tp(self) -> bool:
        return self.type == "TP"

    @property
    def column_stack_group(self) -> Optional[Tuple[str, str]]:
        if self.is_tp and self.lid_fit_type == "外嵌め":
            return "TP_EXTERNAL_LID", self.lid_id
        if not self.is_tp:
            return "NON_TP", self.id
        return None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BoxSpec":
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            type=d.get("type", "TP"),
            width=float(d["width"]),
            length=float(d["length"]),
            height=float(d["height"]),
            fitting_depth=float(d.get("fitting_depth", 10.0)),
            rib_thickness=float(d.get("rib_thickness", 22.0)),
            module_ratio=d.get("module_ratio"),
            description=d.get("description", ""),
            top_support_points=required_support_points(d["id"], d)
        )

@dataclass
class PlacedBox:
    order: int                    # 積載順序 (1, 2, 3, ...)
    box_id: str                   # 箱型番
    x: float                      # 内部計算用の箱本体最小X座標 [mm]
    y: float                      # 内部計算用の箱本体最小Y座標 [mm]
    z: float                      # 内部計算用の箱本体底面Z座標 [mm]
    width: float                  # mm (配置後のX方向寸法。L/Wとは限らない)
    length: float                 # mm (配置後のY方向寸法。L/Wとは限らない)
    height: float                 # mm (配置後のZ方向寸法、蓋含む)
    fitting_depth: float          # mm
    rib_thickness: float          # mm
    rotation: int                 # 0 or 90
    layer_index: int = 0          # 段数インデックス (0, 1, 2, ...)
    supported_by: List[int] = field(default_factory=list) # 下段の箱のorderリスト
    lid_id: str = ""               # 蓋ID（デフォルト: 蓋無）
    lid_thickness: float = 0.0    # 【NEW】蓋の厚さ [mm]
    lid_width: float = 0.0
    lid_length: float = 0.0
    lid_fit_type: str = "なし"

    @property
    def footprint_width(self) -> float:
        if self.lid_fit_type in ("外嵌め", "内嵌め"):
            return max(self.width, self.lid_width)
        return self.width

    @property
    def footprint_length(self) -> float:
        if self.lid_fit_type in ("外嵌め", "内嵌め"):
            return max(self.length, self.lid_length)
        return self.length

    @property
    def footprint_min_x(self) -> float:
        footprint_width = self.footprint_width
        return self.x - (footprint_width - self.width) / 2.0

    @property
    def footprint_min_y(self) -> float:
        footprint_length = self.footprint_length
        return self.y - (footprint_length - self.length) / 2.0

    @property
    def top_z(self) -> float:
        return self.z + self.height

    @property
    def max_x(self) -> float:
        return self.footprint_min_x + self.footprint_width

    @property
    def max_y(self) -> float:
        return self.footprint_min_y + self.footprint_length

    def to_dict(self) -> Dict[str, Any]:
        """Serialize using the combined footprint minimum and top-surface reference."""
        return {
            "order": self.order,
            "box_id": self.box_id,
            "position": {
                "x": round(self.footprint_min_x, 2),
                "y": round(self.footprint_min_y, 2),
                "z": round(self.top_z, 2)
            },
            "dimensions": {
                "width": round(self.width, 2),
                "length": round(self.length, 2),
                "height": round(self.height, 2)
            },
            "rotation": self.rotation,
            "fitting_depth": self.fitting_depth,
            "layer_index": self.layer_index,
            "supported_by": self.supported_by,
            "lid_id": self.lid_id,              # 【NEW】蓋ID
            "lid_thickness": round(self.lid_thickness, 2),  # 【NEW】蓋厚
            "lid_dimensions": {
                "width": round(self.lid_width, 2),
                "length": round(self.lid_length, 2)
            },
            "lid_fit_type": self.lid_fit_type
        }

@dataclass
class PalletSpec:
    length: float = 1200.0        # mm (X軸 長辺 L)
    width: float = 1000.0         # mm (Y軸 短辺 W)
    max_height: float = 1200.0    # mm (Z軸 最大積載高)
    max_x_span: float = 1360.0    # mm (荷山最大L、境界値を含む)
    max_y_span: float = 1100.0    # mm (荷山最大W、境界値を含む)
    height: float = 130.0        # mm (パレット本体高。積載高には含めない)

    def __post_init__(self) -> None:
        for name in ("length", "width", "height", "max_x_span", "max_y_span", "max_height"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                raise ValueError(f"pallet.{name} は0より大きい有限の数値で指定してください")
        if self.max_y_span > self.max_x_span:
            raise ValueError("荷山最大L (max_x_span) は最大W (max_y_span) 以上にしてください")

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PalletSpec":
        defaults = cls()
        values: Dict[str, float] = {}
        for name in ("length", "width", "height", "max_x_span", "max_y_span", "max_height"):
            raw = d.get(name, getattr(defaults, name))
            try:
                if isinstance(raw, bool):
                    raise ValueError("boolean is not a dimension")
                values[name] = float(raw)
                if not math.isfinite(values[name]) or values[name] <= 0:
                    raise ValueError("dimension must be positive and finite")
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"pallet.{name} は0より大きい有限の数値で指定してください") from exc
        length, width = values["length"], values["width"]
        if width > length:
            length, width = width, length
        values.update(length=length, width=width)
        return cls(**values)

@dataclass
class PalletizeSummary:
    total_boxes: int
    total_layers: int
    bounding_box: Dict[str, float]
    volume_efficiency: float
    is_valid_constraints: bool

@dataclass
class PalletizeResult:
    test_name: str
    pallet: PalletSpec
    boxes: List[PlacedBox]
    summary: Dict[str, Any]
    unplaced_boxes: List[Dict[str, Any]] = field(default_factory=list)
    input_boxes_count: int = 0
    input_box_variants: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        placed_count = len(self.boxes)
        return {
            "test_name": self.test_name,
            "coordinate_reference": POSITION_REFERENCE,
            "pallet": asdict(self.pallet),
            "input_boxes_count": self.input_boxes_count,
            "input_box_variants": self.input_box_variants,
            "placed_boxes_count": placed_count,
            "unplaced_boxes_count": max(0, self.input_boxes_count - placed_count),
            "boxes": [b.to_dict() for b in self.boxes],
            "unplaced_boxes": self.unplaced_boxes,
            "summary": self.summary
        }
