"""Geometric support rules for a uniformly loaded, rigid upper pallet."""

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Tuple

Rect = Tuple[float, float, float, float]
Point = Tuple[float, float]
EPS = 1e-9
HEIGHT_TOLERANCE_MM = 3.0
LONG_SUPPORT_MM = 670.0
MIN_HULL_AREA_RATIO = 0.65
MAX_CENTROID_OFFSET_RATIO = 0.25


def required_support_points(box_id: str, record: Dict[str, Any]) -> int:
    value = record.get("top_support_points", 5 if box_id in ("TP331", "TP-331") else 4)
    if isinstance(value, bool) or not isinstance(value, int) or value not in (4, 5):
        raise ValueError(f"{box_id}.top_support_points must be 4 or 5")
    return value


@dataclass(frozen=True)
class TopSurface:
    order: int
    box_id: str
    bounds: Rect
    bottom: float
    top: float
    required_points: int


def _intersection(a: Rect, b: Rect) -> Rect:
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def _positive(rect: Rect) -> bool:
    return rect[2] > rect[0] + EPS and rect[3] > rect[1] + EPS


def _subtract(rect: Rect, cover: Rect) -> List[Rect]:
    overlap = _intersection(rect, cover)
    if not _positive(overlap):
        return [rect]
    x0, y0, x1, y1 = rect
    a, b, c, d = overlap
    return [part for part in ((x0, y0, a, y1), (c, y0, x1, y1),
                              (a, y0, c, b), (a, d, c, y1)) if _positive(part)]


def _contains(rect: Rect, point: Point) -> bool:
    return (rect[0] - EPS <= point[0] <= rect[2] + EPS and
            rect[1] - EPS <= point[1] <= rect[3] + EPS)


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _hull(rectangles: List[Rect]) -> List[Point]:
    points = sorted({(x, y) for r in rectangles for x in (r[0], r[2])
                     for y in (r[1], r[3])})
    if len(points) < 3:
        return points
    halves: List[List[Point]] = []
    for sequence in (points, list(reversed(points))):
        half: List[Point] = []
        for point in sequence:
            while len(half) >= 2 and _cross(half[-2], half[-1], point) <= EPS:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return halves[0] + halves[1]


def _line_support_length(rectangles: List[Rect], axis: int, position: float) -> float:
    other = 1 - axis
    intervals = sorted((r[axis], r[axis + 2]) for r in rectangles
                       if r[other] - EPS <= position <= r[other + 2] + EPS)
    best = 0.0
    start, end = 0.0, -math.inf
    for low, high in intervals:
        if low > end + EPS:
            start, end = low, high
        else:
            end = max(end, high)
        best = max(best, end - start)
    return best


def _polygon_area_centroid(points: List[Point]) -> Tuple[float, Point]:
    pairs = list(zip(points, points[1:] + points[:1]))
    cross = [a[0] * b[1] - b[0] * a[1] for a, b in pairs]
    twice_area = sum(cross)
    if abs(twice_area) <= EPS:
        raise ValueError("Support polygon must have positive area")
    centroid = tuple(sum((a[i] + b[i]) * c for (a, b), c in zip(pairs, cross)) /
                     (3.0 * twice_area) for i in (0, 1))
    return abs(twice_area) / 2.0, (centroid[0], centroid[1])


def _continuous_lengths(rectangles: List[Rect]) -> Tuple[float, float]:
    lengths = []
    for axis in (0, 1):
        best = 0.0
        other = 1 - axis
        for position in sorted({r[other] for r in rectangles} |
                               {r[other + 2] for r in rectangles}):
            best = max(best, _line_support_length(rectangles, axis, position))
        lengths.append(best)
    return lengths[0], lengths[1]


def evaluate_top_support(surfaces: List[TopSurface], pallet_length: float,
                         pallet_width: float, max_x_span: float,
                         max_y_span: float) -> Dict[str, Any]:
    """Recompute exposed contact regions; never trust stored support relations."""
    pallet = (0.0, 0.0, pallet_length, pallet_width)
    intersecting = [s for s in surfaces if _positive(_intersection(s.bounds, pallet))]
    if not intersecting:
        return {"is_valid": False, "violations": ["Upper pallet has no contact support"],
                "support_height": 0.0, "height_tolerance_mm": HEIGHT_TOLERANCE_MM,
                "support_regions": [], "support_boxes": [], "required_points": 4,
                "corner_points": [], "corners_supported": [],
                "center": (pallet_length / 2.0, pallet_width / 2.0),
                "center_supported": False, "support_polygon": [], "balanced": False,
                "continuous_support_x_mm": 0.0, "continuous_support_y_mm": 0.0,
                "opposing_edge_lengths_mm": {"front": 0.0, "back": 0.0, "left": 0.0, "right": 0.0},
                "opposing_support_axis": "",
                "support_polygon_area_mm2": 0.0, "support_area_ratio": 0.0,
                "support_centroid": None, "centroid_offset_mm": None,
                "reference_max_x_span_mm": max_x_span, "reference_max_y_span_mm": max_y_span,
                "multi_corner_boxes": [], "contact_short_side_mm": 0.0,
                "long_edge_exception": False}
    height = max(s.top for s in intersecting)
    regions: List[Rect] = []
    corner_regions: List[Rect] = []
    supporters = []
    exposed_by_box = []
    for surface in intersecting:
        if height - surface.top > HEIGHT_TOLERANCE_MM + EPS:
            continue
        exposed = [surface.bounds]
        for above in intersecting:
            if (above.top > surface.top + EPS and above.bottom <= surface.top + EPS):
                exposed = [part for rect in exposed for part in _subtract(rect, above.bounds)]
        contacting = [r for r in exposed if _positive(_intersection(r, pallet))]
        if contacting:
            corner_regions.extend(contacting)
            regions.extend(_intersection(r, pallet) for r in contacting)
            supporters.append(surface)
            exposed_by_box.append((surface, contacting))

    envelope = (
        min(s.bounds[0] for s in surfaces), min(s.bounds[1] for s in surfaces),
        max(s.bounds[2] for s in surfaces), max(s.bounds[3] for s in surfaces))
    corners = [(x, y) for x in (envelope[0], envelope[2])
               for y in (envelope[1], envelope[3])]
    covered = [any(_contains(r, p) for r in corner_regions) for p in corners]
    center = (pallet_length / 2.0, pallet_width / 2.0)
    center_supported = any(_contains(r, center) for r in regions)
    hull = _hull(regions)
    area, centroid = _polygon_area_centroid(hull)
    area_ratio = area / (max_x_span * max_y_span)
    offset = (abs(centroid[0] - center[0]), abs(centroid[1] - center[1]))
    multi_corner_boxes = [
        {"order": s.order, "box_id": s.box_id, "corner_count": count}
        for s, exposed in exposed_by_box
        for count in [sum(any(_contains(r, p) for r in exposed) for p in corners)]
        if count >= 2
    ]
    balanced = len(hull) >= 3 and all(
        _cross(a, b, center) > EPS * max(1.0, math.hypot(b[0] - a[0], b[1] - a[1]))
        for a, b in zip(hull, hull[1:] + hull[:1])
    )
    required = max((s.required_points for s in supporters), default=4)
    length_x, length_y = _continuous_lengths(regions)
    contact_bounds = (
        min(r[0] for r in regions), min(r[1] for r in regions),
        max(r[2] for r in regions), max(r[3] for r in regions))
    edges = {
        "front": _line_support_length(regions, 0, contact_bounds[1]),
        "back": _line_support_length(regions, 0, contact_bounds[3]),
        "left": _line_support_length(regions, 1, contact_bounds[0]),
        "right": _line_support_length(regions, 1, contact_bounds[2])
    }
    short_side = min(contact_bounds[2] - contact_bounds[0],
                     contact_bounds[3] - contact_bounds[1])
    axis = "XY" if min(edges.values()) >= LONG_SUPPORT_MM - EPS else ""
    exception = not all(covered) and bool(axis)
    violations = []
    if area_ratio < MIN_HULL_AREA_RATIO - EPS:
        violations.append(
            f"Support hull area ratio {area_ratio:.6f} is below 0.65 of configured maximum footprint")
    if (offset[0] >= max_x_span * MAX_CENTROID_OFFSET_RATIO - EPS or
            offset[1] >= max_y_span * MAX_CENTROID_OFFSET_RATIO - EPS):
        violations.append(
            f"Support hull area centroid offset X={offset[0]:.6f}, Y={offset[1]:.6f}mm "
            f"must be less than configured quarter spans X={max_x_span / 4:.6f}, "
            f"Y={max_y_span / 4:.6f}mm")
    if all(covered) and multi_corner_boxes and short_side < LONG_SUPPORT_MM - EPS:
        violations.append(
            f"One box supports multiple outer corners; contact footprint short side "
            f"{short_side:.6f}mm must be at least 670mm")
    if not balanced:
        violations.append("Upper pallet center is outside or on the boundary of the support polygon")
    if not all(covered) and not exception:
        violations.append("Top outer corners lack same-height support; all four contact edges, including the short sides, each need continuous 670mm support")
    if required == 5 and not center_supported:
        violations.append("Five-point support requires contact at the upper pallet center")
    return {
        "is_valid": not violations, "violations": violations,
        "support_height": height, "height_tolerance_mm": HEIGHT_TOLERANCE_MM,
        "support_boxes": [{"order": s.order, "box_id": s.box_id, "top_z": s.top}
                          for s in supporters],
        "support_regions": regions, "required_points": required,
        "corner_points": corners, "corners_supported": covered,
        "center": center, "center_supported": center_supported,
        "support_polygon": hull, "balanced": balanced,
        "continuous_support_x_mm": length_x, "continuous_support_y_mm": length_y,
        "opposing_edge_lengths_mm": edges, "opposing_support_axis": axis,
        "support_polygon_area_mm2": area, "support_area_ratio": area_ratio,
        "support_centroid": centroid, "centroid_offset_mm": offset,
        "reference_max_x_span_mm": max_x_span, "reference_max_y_span_mm": max_y_span,
        "multi_corner_boxes": multi_corner_boxes, "contact_short_side_mm": short_side,
        "long_edge_exception": exception
    }
