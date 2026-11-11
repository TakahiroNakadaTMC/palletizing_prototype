import unittest
from pathlib import Path
from unittest.mock import patch

from algorithm_programmer.cli import main, resolve_box_specs, resolve_pallet_spec
from algorithm_programmer.models import BoxSpec


class ResolvePalletSpecTest(unittest.TestCase):
    def setUp(self):
        self.pallet_database = {
            "pallets": {
                "PALLET_A": {
                    "id": "PALLET_A", "length": 1200, "width": 1000, "height": 130,
                    "suppliers": ["Supplier A"],
                },
                "__STANDARD_1200_1000_130__": {
                    "id": "__STANDARD_1200_1000_130__",
                    "length": 1200, "width": 1000, "height": 130, "suppliers": [],
                },
            }
        }
        self.test_case = {
            "pallet_id": "PALLET_A",
            "supplier_name": "Supplier A",
            "pallet": {"max_x_span": 1300, "max_y_span": 1050, "max_height": 1000},
        }

    def test_resolves_physical_dimensions_from_pallet_id(self):
        spec = resolve_pallet_spec(self.test_case, self.pallet_database)
        self.assertEqual((spec.length, spec.width, spec.height), (1200, 1000, 130))
        self.assertEqual((spec.max_x_span, spec.max_y_span, spec.max_height), (1300, 1050, 1000))

    def test_pallet_database_dimensions_override_legacy_case_values(self):
        case = {
            **self.test_case,
            "pallet": {
                "length": 999, "width": 888, "height": 77,
                "max_x_span": 1300, "max_y_span": 1050, "max_height": 1000,
            },
        }
        spec = resolve_pallet_spec(case, self.pallet_database)
        self.assertEqual((spec.length, spec.width, spec.height), (1200, 1000, 130))

    def test_standard_pallet_is_available_without_supplier_association(self):
        case = {
            "pallet_id": "__STANDARD_1200_1000_130__",
            "pallet": {"max_x_span": 1360, "max_y_span": 1100, "max_height": 1200},
        }
        spec = resolve_pallet_spec(case, self.pallet_database)
        self.assertEqual((spec.length, spec.width, spec.height), (1200, 1000, 130))

    def test_rejects_missing_pallet_id(self):
        case = dict(self.test_case)
        case.pop("pallet_id")
        with self.assertRaisesRegex(ValueError, "pallet_id"):
            resolve_pallet_spec(case, self.pallet_database)

    def test_rejects_supplier_mismatch(self):
        case = dict(self.test_case, supplier_name="Other supplier")
        with self.assertRaisesRegex(ValueError, "仕入先"):
            resolve_pallet_spec(case, self.pallet_database)


class ResolveBoxSpecsTest(unittest.TestCase):
    def setUp(self):
        self.box_database = {
            "BOX_A": {
                "id": "BOX_A", "name": "Box A", "type": "TP",
                "width": 300, "length": 400, "height": 200,
                "fitting_depth": 10, "rib_thickness": 20,
                "compatible_lids": ["LID_A"],
            },
            "BOX_UNUSED": {
                "id": "BOX_UNUSED", "name": "Unused", "type": "TP",
                "width": 500, "length": 600, "height": 200,
                "fitting_depth": 10, "rib_thickness": 20,
            },
        }
        self.lid_database = {
            "NO_LID": {
                "id": "NO_LID", "type": "NONE", "width": 0, "length": 0,
                "thickness": 0, "fit_type": "なし",
            },
            "LID_A": {
                "id": "LID_A", "type": "TP", "width": 320, "length": 420,
                "thickness": 5, "fit_type": "外嵌め",
            },
            "LID_UNUSED": {
                "id": "LID_UNUSED", "type": "TP", "width": 100, "length": 100,
                "thickness": 1, "fit_type": "内嵌め",
            },
        }

    def test_selects_only_box_and_lid_variants_used_by_case(self):
        specs, box_list = resolve_box_specs(
            [{"box_id": "BOX_A", "count": 2, "lid_id": "LID_A"}],
            self.box_database,
            self.lid_database,
        )
        self.assertEqual(list(specs), [("BOX_A", "LID_A")])
        selected = specs[("BOX_A", "LID_A")]
        self.assertIsInstance(selected, BoxSpec)
        self.assertEqual(
            (selected.lid_width, selected.lid_length, selected.lid_thickness,
             selected.lid_fit_type),
            (320, 420, 5, "外嵌め"),
        )
        self.assertEqual(box_list[0]["lid_id"], "LID_A")

    def test_uses_no_lid_record_when_case_omits_lid_id(self):
        specs, box_list = resolve_box_specs(
            [{"box_id": "BOX_A", "count": 1}],
            self.box_database,
            self.lid_database,
        )
        self.assertEqual(list(specs), [("BOX_A", "NO_LID")])
        self.assertEqual(box_list[0]["lid_id"], "NO_LID")

    def test_rejects_unknown_or_incompatible_lid(self):
        with self.assertRaisesRegex(ValueError, "蓋DB"):
            resolve_box_specs(
                [{"box_id": "BOX_A", "lid_id": "MISSING"}],
                self.box_database,
                self.lid_database,
            )
        with self.assertRaisesRegex(ValueError, "対応していません"):
            resolve_box_specs(
                [{"box_id": "BOX_A", "lid_id": "LID_UNUSED"}],
                self.box_database,
                self.lid_database,
            )


class CliMainRuntimeTest(unittest.TestCase):
    def test_uses_loaded_catalog_pallet_snapshot(self):
        catalog = dict(
            parts={"P-1": dict(id="P-1", supplier_name="S", box_name="B", box_model_id="M", lid_id="L")},
            models={},
            lids={},
            cases=dict(
                test_cases={"c1": dict(
                    name="c1", description="d", supplier_name="S",
                    pallet_id="__STANDARD_1200_1000_130__",
                    pallet=dict(max_x_span=1360, max_y_span=1100, max_height=1200),
                    box_list=[dict(part_number="P-1", count=1)],
                )},
                approval_state={"c1": True},
            ),
            pallets={"pallets": {"__STANDARD_1200_1000_130__": {
                "id": "__STANDARD_1200_1000_130__", "length": 1200, "width": 1000, "height": 130, "suppliers": []
            }}},
        )
        result = dict(
            summary=dict(
                total_boxes=1, total_layers=1,
                bounding_box=dict(x_span=1.0, y_span=1.0, max_z=1.0),
                volume_efficiency_percent=1.0,
                is_valid=True, total_height=1.0, warnings=[], violations=[],
            ),
            algorithm_mode="single",
            part_counts=[dict(part_number="P-1", box_name="B", placed_count=1, input_count=1, unplaced_count=0)],
            unplaced_boxes=[],
        )

        def _catalog_pallets(_root: Path, pallet_database=None):
            self.assertEqual(pallet_database, catalog["pallets"])
            return pallet_database

        with patch("algorithm_programmer.cli.load_catalog", return_value=(catalog, "rev")), \
             patch("algorithm_programmer.cli.catalog_pallets", side_effect=_catalog_pallets), \
             patch("algorithm_programmer.cli.validate_staged_cases"), \
             patch("algorithm_programmer.cli.resolve_pallet_spec", return_value=object()), \
             patch("algorithm_programmer.cli.run_catalog_case", return_value=result), \
             patch("sys.argv", ["cli.py", "--catalog-case", "c1"]):
            main()


if __name__ == "__main__":
    unittest.main()
