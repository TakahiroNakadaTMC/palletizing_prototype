import unittest

from algorithm_programmer.models import (
    POSITION_REFERENCE,
    BoxSpec,
    PalletSpec,
    PalletizeResult,
    PlacedBox
)


class PlacementCoordinateTests(unittest.TestCase):
    def make_placed_box(self, fit_type, lid_width, lid_length):
        return PlacedBox(
            order=1,
            box_id="TEST",
            x=100.0,
            y=200.0,
            z=30.0,
            width=300.0,
            length=200.0,
            height=315.0,
            fitting_depth=10.0,
            rib_thickness=2.0,
            rotation=0,
            lid_id="TEST-LID",
            lid_thickness=15.0,
            lid_width=lid_width,
            lid_length=lid_length,
            lid_fit_type=fit_type
        )

    def test_external_lid_position_uses_combined_min_corner_and_top(self):
        placed_box = self.make_placed_box("外嵌め", 340.0, 220.0)

        result_box = placed_box.to_dict()

        self.assertEqual(result_box["position"], {"x": 80.0, "y": 190.0, "z": 345.0})
        self.assertEqual(result_box["dimensions"], {
            "width": 300.0, "length": 200.0, "height": 315.0
        })

    def test_inner_lid_smaller_than_box_keeps_box_as_combined_bounds(self):
        placed_box = self.make_placed_box("内嵌め", 280.0, 180.0)

        result_box = placed_box.to_dict()

        self.assertEqual(result_box["position"], {"x": 100.0, "y": 200.0, "z": 345.0})
        self.assertEqual(placed_box.max_x - placed_box.footprint_min_x, 300.0)
        self.assertEqual(placed_box.max_y - placed_box.footprint_min_y, 200.0)

    def test_inner_lid_larger_than_box_expands_combined_bounds(self):
        placed_box = self.make_placed_box("内嵌め", 320.0, 240.0)

        result_box = placed_box.to_dict()

        self.assertEqual(result_box["position"], {"x": 90.0, "y": 180.0, "z": 345.0})

    def test_rotated_lid_uses_rotated_xy_dimensions(self):
        placed_box = PlacedBox(
            order=1, box_id="ROTATED", x=100.0, y=200.0, z=0.0,
            width=200.0, length=300.0, height=115.0,
            fitting_depth=10.0, rib_thickness=2.0, rotation=90,
            lid_id="ROTATED-LID", lid_thickness=15.0,
            lid_width=240.0, lid_length=220.0, lid_fit_type="外嵌め"
        )

        result_box = placed_box.to_dict()

        self.assertEqual(result_box["position"], {"x": 80.0, "y": 200.0, "z": 115.0})
        self.assertEqual(result_box["dimensions"]["width"], 200.0)
        self.assertEqual(result_box["dimensions"]["length"], 300.0)

    def test_uncovered_box_uses_its_top_surface(self):
        placed_box = PlacedBox(
            order=1, box_id="NO-LID", x=12.0, y=34.0, z=56.0,
            width=100.0, length=80.0, height=120.0,
            fitting_depth=10.0, rib_thickness=2.0, rotation=0
        )

        self.assertEqual(placed_box.to_dict()["position"], {
            "x": 12.0, "y": 34.0, "z": 176.0
        })

    def test_lid_footprint_dimensions_include_inner_and_outer_lids(self):
        inner_lid_box = BoxSpec(
            id="INNER", name="Inner", type="TP", width=300.0, length=200.0,
            height=100.0, fitting_depth=10.0, rib_thickness=2.0,
            lid_fit_type="内嵌め", lid_width=280.0, lid_length=180.0
        )
        outer_lid_box = BoxSpec(
            id="OUTER", name="Outer", type="TP", width=300.0, length=200.0,
            height=100.0, fitting_depth=10.0, rib_thickness=2.0,
            lid_fit_type="外嵌め", lid_width=320.0, lid_length=220.0
        )

        self.assertEqual((inner_lid_box.footprint_width, inner_lid_box.footprint_length),
                         (300.0, 200.0))
        self.assertEqual((outer_lid_box.footprint_width, outer_lid_box.footprint_length),
                         (320.0, 220.0))

    def test_result_identifies_coordinate_reference(self):
        result = PalletizeResult(
            test_name="coordinate-test", pallet=PalletSpec(), boxes=[], summary={}
        ).to_dict()

        self.assertEqual(result["coordinate_reference"], POSITION_REFERENCE)


if __name__ == "__main__":
    unittest.main()