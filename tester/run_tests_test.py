import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tester.run_tests import run_catalog_tests


class RunCatalogTestsRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.case = dict(
            name="one",
            supplier_name="S",
            skid_id="KEY-A",
            box_list=[dict(part_number="P-1", count=1)],
        )
        self.catalog = dict(
            models={},
            lids={},
            parts={"P-1": dict(id="P-1", supplier_name="S", box_name="B", box_model_id="M", lid_id="L")},
            skids={"KEY-A": dict(
                supplier_name="S", pallet_id="__STANDARD_1200_1000_130__",
                pallet=dict(max_x_span=1360.0, max_y_span=1100.0, max_height=1200.0),
                part_numbers=["P-1"])},
            cases=dict(test_cases={"one": self.case}, approval_state={"one": True}),
            pallets={"pallets": {"__STANDARD_1200_1000_130__": {
                "id": "__STANDARD_1200_1000_130__", "length": 1200, "width": 1000, "height": 130, "suppliers": []
            }}},
        )
        self.pallets = {"pallets": {"__STANDARD_1200_1000_130__": {
            "id": "__STANDARD_1200_1000_130__", "length": 1200, "width": 1000, "height": 130, "suppliers": []
        }}}
        self.result = dict(
            test_name="one",
            input_mode="part_number",
            schema_version=2,
            catalog_revision="rev",
            input_boxes_count=1,
            placed_boxes_count=1,
            unplaced_boxes_count=0,
            boxes=[],
            unplaced_boxes=[],
            part_counts=[],
            summary=dict(is_valid=True, violations=[]),
        )

    def test_manifest_has_source_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            with patch("box_research.catalog_store.load_catalog", return_value=(self.catalog, "rev")), \
                 patch("box_research.catalog_store.catalog_pallets", return_value=self.pallets), \
                 patch("algorithm_programmer.catalog.run_catalog_case", return_value=self.result):
                rc = run_catalog_tests(output)
            self.assertEqual(rc, 0)
            manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source"], "catalog_store")
            self.assertEqual(manifest["catalog_revision"], "rev")
            self.assertEqual(manifest["counts"]["cases"], 1)
            self.assertTrue((output / "result_one.json").exists())

    def test_default_output_dir_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("tester.run_tests.DEFAULT_RESULTS_ROOT", Path(directory)), \
                 patch("box_research.catalog_store.load_catalog", return_value=(self.catalog, "rev")), \
                 patch("box_research.catalog_store.catalog_pallets", return_value=self.pallets), \
                 patch("algorithm_programmer.catalog.run_catalog_case", return_value=self.result):
                rc = run_catalog_tests()
            self.assertEqual(rc, 0)
            created = list(Path(directory).glob("run_*"))
            self.assertEqual(len(created), 1)
            self.assertTrue((created[0] / "run_manifest.json").exists())

    def test_uses_loaded_catalog_pallet_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"

            def _catalog_pallets(_root, pallet_database=None):
                self.assertEqual(pallet_database, self.catalog["pallets"])
                return pallet_database

            with patch("box_research.catalog_store.load_catalog", return_value=(self.catalog, "rev")), \
                 patch("box_research.catalog_store.catalog_pallets", side_effect=_catalog_pallets), \
                 patch("algorithm_programmer.catalog.run_catalog_case", return_value=self.result):
                rc = run_catalog_tests(output)
            self.assertEqual(rc, 0)

    def test_incomplete_skid_is_error_not_fallback_or_silent_skip(self):
        self.catalog["skids"]["KEY-A"]["pallet_id"] = None
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out"
            with patch("box_research.catalog_store.load_catalog", return_value=(self.catalog, "rev")), \
                 patch("box_research.catalog_store.catalog_pallets", return_value=self.pallets), \
                 patch("algorithm_programmer.catalog.run_catalog_case") as calculate:
                self.assertEqual(run_catalog_tests(output), 1)
                calculate.assert_not_called()
            manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["cases"], 1)
            self.assertEqual(manifest["counts"]["errors"], 1)
            self.assertIn("未登録", manifest["cases"][0]["error"])
            self.assertFalse((output / "result_one.json").exists())

if __name__ == "__main__":
    unittest.main()
