"""
パレタイズデータモデル定義 (models.py)
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

@dataclass
class BoxSpec:
    id: str
    name: str
    type: str                     # "TP" or "NON_TP"
    width: float                  # mm (外寸幅)
    length: float                 # mm (外寸奥行)
    height: float                 # mm (外寸高さ)
    fitting_depth: float          # mm (嵌合沈み込み深さ)
    rib_thickness: float          # mm (側面リブ厚み)
    module_ratio: Optional[str] = None  # "1x1", "1.5x1", "2x1", etc.
    description: str = ""

    @property
    def is_tp(self) -> bool:
        return self.type == "TP"

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
            description=d.get("description", "")
        )

@dataclass
class PlacedBox:
    order: int                    # 積載順序 (1, 2, 3, ...)
    box_id: str                   # 箱型番
    x: float                      # mm
    y: float                      # mm
    z: float                      # mm (底面Z座標)
    width: float                  # mm (配置後のX方向寸法)
    length: float                 # mm (配置後のY方向寸法)
    height: float                 # mm (配置後のZ方向寸法)
    fitting_depth: float          # mm
    rib_thickness: float          # mm
    rotation: int                 # 0 or 90
    layer_index: int = 0          # 段数インデックス (0, 1, 2, ...)
    supported_by: List[int] = field(default_factory=list) # 下段の箱のorderリスト

    @property
    def top_z(self) -> float:
        return self.z + self.height

    @property
    def max_x(self) -> float:
        return self.x + self.width

    @property
    def max_y(self) -> float:
        return self.y + self.length

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order": self.order,
            "box_id": self.box_id,
            "position": {
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "z": round(self.z, 2)
            },
            "dimensions": {
                "width": round(self.width, 2),
                "length": round(self.length, 2),
                "height": round(self.height, 2)
            },
            "rotation": self.rotation,
            "fitting_depth": self.fitting_depth,
            "layer_index": self.layer_index,
            "supported_by": self.supported_by
        }

@dataclass
class PalletSpec:
    width: float = 1200.0         # mm (X軸 長辺)
    length: float = 1000.0        # mm (Y軸 短辺)
    max_height: float = 1200.0    # mm (Z軸 最大積載高)
    max_x_span: float = 1360.0    # mm (長辺荷姿許容上限: <1360mm)
    min_y_span: float = 800.0     # mm (短辺荷姿最小幅: >=800mm)
    max_y_span: float = 1100.0    # mm (短辺荷姿最大幅: <1100mm)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PalletSpec":
        return cls(
            width=float(d.get("width", 1200.0)),
            length=float(d.get("length", 1000.0)),
            max_height=float(d.get("max_height", 1200.0)),
            max_x_span=float(d.get("max_x_span", 1360.0)),
            min_y_span=float(d.get("min_y_span", 800.0)),
            max_y_span=float(d.get("max_y_span", 1100.0))
        )

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "pallet": asdict(self.pallet),
            "placed_boxes_count": len(self.boxes),
            "boxes": [b.to_dict() for b in self.boxes],
            "unplaced_boxes": self.unplaced_boxes,
            "summary": self.summary
        }
