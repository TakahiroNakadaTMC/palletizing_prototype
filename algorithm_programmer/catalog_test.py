"""品番の数量保存と共通モデルによる配置の回帰テスト。"""

import copy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch

from algorithm_programmer.catalog import run_catalog_case
from algorithm_programmer.cli import resolve_box_specs, resolve_pallet_spec
from algorithm_programmer.models import BoxSpec, PlacedBox
from algorithm_programmer.palletizer import Palletizer
from box_research.catalog_store import catalog_pallets, load_catalog
from box_research.database_validation import STANDARD_PALLET_ID
from supervisor.validate import PalletizeValidator
from tester.run_tests import run_catalog_tests


ROOT = Path(__file__).resolve().parent.parent


class CatalogCalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.revision = load_catalog(ROOT)
        cls.pallets = catalog_pallets(ROOT)

    def calculate(self, case, catalog=None):
        return run_catalog_case(case["name"], case, catalog or self.catalog,
                                resolve_pallet_spec(case, self.pallets), self.revision)

    def assert_quantities(self, result, case, catalog=None):
        catalog = catalog or self.catalog
        expected = Counter()
        for row in case["box_list"]:
            expected[row["part_number"]] += row["count"]
        placed = Counter(box["part_number"] for box in result["boxes"])
        missing = Counter({item["part_number"]: item["count"] for item in result["unplaced_boxes"]})
        self.assertEqual(placed + missing, expected)
        self.assertEqual(result["input_boxes_count"], sum(expected.values()))
        self.assertEqual(result["placed_boxes_count"], sum(placed.values()))
        self.assertEqual(result["unplaced_boxes_count"], sum(missing.values()))
        self.assertEqual([box["order"] for box in result["boxes"]],
                         list(range(1, sum(placed.values()) + 1)))
        for row in result["part_counts"]:
            part = row["part_number"]
            self.assertEqual((row["input_count"], row["placed_count"], row["unplaced_count"]),
                             (expected[part], placed[part], missing[part]))
        for row in result["boxes"] + result["input_parts"] + result["part_counts"] + result["unplaced_boxes"]:
            part = catalog["parts"][row["part_number"]]
            for key in ("supplier_name", "box_name", "box_model_id", "lid_id"):
                self.assertEqual(row[key], part[key])
            self.assertEqual(row["box_id"], part["box_name"])
        by_order = {box["order"]: box for box in result["boxes"]}
        for field in ("support_boxes", "multi_corner_boxes"):
            for row in result["summary"]["top_support"].get(field, []):
                source = by_order[row["order"]]
                for key in ("part_number", "box_model_id", "box_id", "lid_id"):
                    self.assertEqual(row[key], source[key])
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["allocation_method"], "input_order")

    def independently_validate(self, result, catalog=None):
        catalog = catalog or self.catalog
        if result["test_name"] not in catalog.get("cases", {}).get("test_cases", {}):
            catalog = copy.deepcopy(catalog)
            catalog.setdefault("cases", {}).setdefault("test_cases", {})[result["test_name"]] = dict(
                name=result["test_name"], supplier_name=result["supplier_name"], pallet_id=result["pallet_id"],
                pallet={key: result["pallet"][key] for key in ("max_x_span", "max_y_span", "max_height")},
                box_list=[dict(part_number=row["part_number"], count=row["count"])
                          for row in result["input_parts"]])
        validator = PalletizeValidator(catalog["models"], catalog["lids"], catalog, self.revision, self.pallets)
        return validator.validate_data(result)

    def synthetic(self):
        model = dict(id="共通", type="NON_TP", width=400, length=600, height=200,
                     fitting_depth=10, rib_thickness=15, top_support_points=4,
                     compatible_lids=[])
        data = dict(models={"共通": model}, lids={
            "無蓋": dict(id="無蓋", type="NONE", fit_type="なし", width=0, length=0, thickness=0),
        }, parts={
            "A": dict(id="A", supplier_name="仕入先", box_name="現場A", box_model_id="共通", lid_id="無蓋"),
            "B": dict(id="B", supplier_name="仕入先", box_name="現場B", box_model_id="共通", lid_id="無蓋"),
        })
        case = dict(name="fixture", description="検証", supplier_name="仕入先",
                    pallet_id=STANDARD_PALLET_ID,
                    pallet=dict(max_x_span=1200, max_y_span=1000, max_height=600),
                    box_list=[dict(part_number="A", count=9), dict(part_number="B", count=9)])
        return data, case

    def test_shared_non_tp_model_and_quantities(self):
        case = self.catalog["cases"]["test_cases"]["othics_6"]
        result = self.calculate(case)
        self.assertEqual(result["algorithm_mode"], "single")
        self.assertEqual({box["box_model_id"] for box in result["boxes"]}, {"サンボックス#22H"})
        self.assertEqual({box["box_id"] for box in result["boxes"]}, {"NP22C", "NPP24"})
        self.assert_quantities(result, case)
        self.assertTrue(result["summary"]["is_valid"])
        self.assertTrue(self.independently_validate(result)["is_pass"])
        self.assertTrue(any(
            box["supported_by"] and any(
                result["boxes"][order - 1]["part_number"] != box["part_number"]
                for order in box["supported_by"])
            for box in result["boxes"]))

    def test_shared_tp_model_and_quantities(self):
        case = copy.deepcopy(self.catalog["cases"]["test_cases"]["aisin_7"])
        case["name"] = "tp_alias_fixture"
        case["box_list"] = (self.catalog["cases"]["test_cases"]["aisin_9"]["box_list"]
                            + case["box_list"])
        result = self.calculate(case)
        self.assertEqual(result["algorithm_mode"], "single")
        self.assertEqual({box["box_model_id"] for box in result["boxes"]}, {"TP364"})
        self.assertEqual({box["box_id"] for box in result["boxes"]}, {"SPZ36404", "SPZ36406"})
        self.assert_quantities(result, case)
        self.assertTrue(self.independently_validate(result)["is_pass"])

    def test_partial_placement_allocates_in_input_order(self):
        data, case = self.synthetic()
        result = self.calculate(case, data)
        self.assert_quantities(result, case, data)
        self.assertGreater(result["unplaced_boxes_count"], 0)
        self.assertEqual(result["part_counts"][0]["unplaced_count"], 0)
        self.assertEqual([box["part_number"] for box in result["boxes"]],
                         ["A"] * 9 + ["B"] * (result["placed_boxes_count"] - 9))
        case["box_list"].reverse()
        reversed_result = self.calculate(case, data)
        self.assertEqual(reversed_result["boxes"][0]["part_number"], "B")
        self.assertEqual(result["placed_boxes_count"], reversed_result["placed_boxes_count"])
        self.assertEqual([box["position"] for box in result["boxes"]],
                         [box["position"] for box in reversed_result["boxes"]])

    def test_repeated_part_rows_are_counted_once(self):
        data, case = self.synthetic()
        case["box_list"] = [dict(part_number="A", count=3), dict(part_number="B", count=2),
                            dict(part_number="A", count=2)]
        result = self.calculate(case, data)
        self.assert_quantities(result, case, data)
        self.assertEqual([row["count"] for row in result["input_parts"]], [5, 2])
        self.assertEqual(len(result["part_counts"]), 2)

    def test_same_dimensions_do_not_merge_different_models(self):
        data, case = self.synthetic()
        data["models"]["別箱"] = dict(data["models"]["共通"], id="別箱")
        data["parts"]["B"]["box_model_id"] = "別箱"
        result = self.calculate(case, data)
        self.assertEqual(result["algorithm_mode"], "mixed")
        self.assert_quantities(result, case, data)
        self.assertTrue(self.independently_validate(result, data)["is_pass"])
        for box in result["boxes"]:
            for order in box["supported_by"]:
                self.assertEqual(box["box_model_id"], result["boxes"][order - 1]["box_model_id"])

    def test_same_model_with_different_lids_is_mixed_and_keeps_fixed_lids(self):
        data, case = self.synthetic()
        data["lids"]["薄蓋"] = dict(id="薄蓋", type="OTHER", fit_type="内嵌め",
                                   length=600, width=400, thickness=5)
        data["models"]["共通"]["compatible_lids"] = ["薄蓋"]
        data["parts"]["B"]["lid_id"] = "薄蓋"
        result = self.calculate(case, data)
        self.assertEqual(result["algorithm_mode"], "mixed")
        self.assert_quantities(result, case, data)
        self.assertTrue(self.independently_validate(result, data)["is_pass"])

    def test_no_placement_retains_all_part_quantities_and_reasons(self):
        data, case = self.synthetic()
        case["pallet"]["max_height"] = 100
        result = self.calculate(case, data)
        self.assertEqual(result["boxes"], [])
        self.assertFalse(result["summary"]["is_valid"])
        self.assert_quantities(result, case, data)
        self.assertTrue(all(row["reason"] for row in result["unplaced_boxes"]))

    def test_invalid_inputs_are_explicit_errors(self):
        for field, value in (("part_number", "UNKNOWN"), ("count", 0), ("count", True),
                             ("count", 1.5), ("count", 501), ("lid_id", "無蓋"),
                             ("box_id", "現場A")):
            with self.subTest(field=field, value=value):
                data, case = self.synthetic()
                case["box_list"][0][field] = value
                with self.assertRaises(ValueError):
                    self.calculate(case, data)
        data, case = self.synthetic()
        case["supplier_name"] = "別仕入先"
        with self.assertRaises(ValueError):
            self.calculate(case, data)
        case["box_list"] = []
        with self.assertRaises(ValueError):
            self.calculate(case, data)

    def test_incompatible_catalog_lid_is_not_silently_ignored(self):
        data, case = self.synthetic()
        data["parts"]["A"]["lid_id"] = "未登録"
        with self.assertRaises(ValueError):
            self.calculate(case, data)

    def test_rename_does_not_change_physical_layout(self):
        data, case = self.synthetic()
        original = self.calculate(case, data)
        data["models"]["変更後"] = dict(data["models"].pop("共通"), id="変更後")
        for part in data["parts"].values():
            part["box_model_id"] = "変更後"
        renamed = self.calculate(case, data)
        self.assertEqual(original["placed_boxes_count"], renamed["placed_boxes_count"])
        self.assertEqual([box["position"] for box in original["boxes"]],
                         [box["position"] for box in renamed["boxes"]])
        self.assert_quantities(renamed, case, data)

    def test_engine_overallocation_is_rejected(self):
        data, case = self.synthetic()
        reference = self.calculate(case, data)
        case["box_list"] = [dict(part_number="A", count=1)]
        geometry = copy.deepcopy(reference)
        geometry["boxes"] = [copy.deepcopy(geometry["boxes"][0]) for _ in range(2)]
        for order, box in enumerate(geometry["boxes"], 1):
            box["order"] = order
            box["box_id"] = "共通"
        with patch("algorithm_programmer.catalog.Palletizer") as engine:
            engine.return_value.run.return_value.to_dict.return_value = geometry
            with self.assertRaisesRegex(RuntimeError, "投入数量"):
                self.calculate(case, data)

    def test_non_tp_bad_offset_multiple_support_and_different_model_are_rejected(self):
        spec = BoxSpec("共通", "共通", "NON_TP", 400, 600, 200, 10, 15)
        other = BoxSpec("別箱", "別箱", "NON_TP", 400, 600, 200, 10, 15)
        engine = Palletizer({"共通": spec, "別箱": other})
        lower = PlacedBox(1, "共通", 0, 0, 0, 400, 600, 200, 10, 15, 0)
        upper = PlacedBox(2, "共通", 0, 0, 190, 400, 600, 200, 10, 15, 0)
        self.assertTrue(engine._column_stack_is_allowed(spec, upper, [lower]))
        upper.x = 0.02
        self.assertFalse(engine._column_stack_is_allowed(spec, upper, [lower]))
        upper.x = 0
        self.assertFalse(engine._column_stack_is_allowed(spec, upper, [lower, copy.copy(lower)]))
        upper.box_id = "別箱"
        self.assertFalse(engine._column_stack_is_allowed(other, upper, [lower]))

    def test_ordinary_tp_and_external_tp_keep_cross_model_rules(self):
        for fit_type in ("内嵌め", "外嵌め"):
            with self.subTest(fit_type=fit_type):
                data, case = self.synthetic()
                data["models"]["共通"].update(type="TP", compatible_lids=["TP蓋"])
                data["models"]["別箱"] = dict(data["models"]["共通"], id="別箱")
                data["lids"]["TP蓋"] = dict(id="TP蓋", type="TP", fit_type=fit_type,
                                           width=400, length=600, thickness=5)
                data["parts"]["B"]["box_model_id"] = "別箱"
                for part in data["parts"].values():
                    part["lid_id"] = "TP蓋"
                result = self.calculate(case, data)
                self.assertEqual(result["algorithm_mode"], "mixed")
                self.assert_quantities(result, case, data)
                self.assertTrue(self.independently_validate(result, data)["is_pass"])
                self.assertTrue(any(
                    box["box_model_id"] != result["boxes"][order - 1]["box_model_id"]
                    for box in result["boxes"] for order in box["supported_by"]))

    def test_cli_saved_and_standalone_part_cases_and_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.json"
            command = [sys.executable, str(ROOT / "algorithm_programmer" / "cli.py")]
            saved = subprocess.run(command + ["--catalog-case", "othics_6", "-o", str(target)],
                                   capture_output=True, encoding="utf-8")
            self.assertEqual(saved.returncode, 0, saved.stderr)
            saved_data = json.loads(target.read_text(encoding="utf-8"))
            case = self.catalog["cases"]["test_cases"]["othics_6"]
            self.assert_quantities(saved_data, case)
            source = Path(directory) / "case.json"
            source.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
            standalone = subprocess.run(command + [str(source), "-o", str(target)],
                                        capture_output=True, encoding="utf-8")
            self.assertEqual(standalone.returncode, 0, standalone.stderr)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), saved_data)
            legacy = subprocess.run(command + [str(ROOT / "test_programmer" / "test_cases" / "othics_6.json"),
                                               "-o", str(target)], capture_output=True, encoding="utf-8")
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            self.assertNotIn("schema_version", json.loads(target.read_text(encoding="utf-8")))
            invalid = subprocess.run(command + ["--catalog-case", "UNKNOWN"],
                                     capture_output=True, encoding="utf-8")
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("UNKNOWN", invalid.stderr)
            ambiguous = subprocess.run(command + [str(source), "--catalog-case", "othics_6"],
                                       capture_output=True, encoding="utf-8")
            self.assertNotEqual(ambiguous.returncode, 0)
            invalid_geometry = subprocess.run(
                command + ["--catalog-case", "othics_m20", "-o", str(target)],
                capture_output=True, encoding="utf-8")
            self.assertEqual(invalid_geometry.returncode, 1, invalid_geometry.stderr)
            self.assertFalse(json.loads(target.read_text(encoding="utf-8"))["summary"]["is_valid"])
            protected = subprocess.run(
                command + ["--catalog-case", "othics_6", "-o",
                           str(ROOT / "tester" / "results" / "protected_test.json")],
                capture_output=True, encoding="utf-8")
            self.assertNotEqual(protected.returncode, 0)
            self.assertIn("旧結果フォルダ", protected.stderr)

    def test_batch_isolated_outputs_adoption_errors_and_manifest(self):
        data = copy.deepcopy(self.catalog)
        selected = self.catalog["cases"]["test_cases"]["othics_6"]
        data["cases"] = dict(test_cases={"ok": selected, "bad": selected, "skip": selected},
                             approval_state={"ok": True, "bad": True, "skip": False})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            stdout, stderr = StringIO(), StringIO()
            with patch("box_research.catalog_store.load_catalog", return_value=(data, "revision")), \
                 patch("algorithm_programmer.catalog.run_catalog_case", side_effect=[
                     self.calculate(selected), ValueError("テスト用入力エラー")]), \
                 redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(run_catalog_tests(output), 1)
            self.assertIn("ERROR [bad]: テスト用入力エラー", stderr.getvalue())
            self.assertIn("PASS [ok]", stdout.getvalue())
            manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["cases"], 2)
            self.assertEqual(manifest["counts"]["errors"], 1)
            self.assertTrue((output / "result_ok.json").exists())
            self.assertFalse((output / "result_bad.json").exists())
            self.assertFalse((output / "result_skip.json").exists())
            self.assertEqual(manifest["cases"][1]["error"], "テスト用入力エラー")
            with self.assertRaises(FileExistsError):
                run_catalog_tests(output)
            with self.assertRaises(ValueError):
                run_catalog_tests(ROOT / "tester" / "results")

    def test_batch_exit_code_distinguishes_unplaced_from_constraint_fail(self):
        data = copy.deepcopy(self.catalog)
        case = self.catalog["cases"]["test_cases"]["othics_6"]
        data["cases"] = dict(test_cases={"one": case}, approval_state={"one": True})
        result = self.calculate(case)
        self.assertGreater(result["unplaced_boxes_count"], 0)
        with tempfile.TemporaryDirectory() as directory:
            for valid in (True, False):
                result["summary"]["is_valid"] = valid
                output = Path(directory) / str(valid)
                with patch("box_research.catalog_store.load_catalog", return_value=(data, "revision")), \
                     patch("algorithm_programmer.catalog.run_catalog_case", return_value=result), \
                     redirect_stdout(StringIO()):
                    self.assertEqual(run_catalog_tests(output), 0 if valid else 1)
                manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["counts"]["failed"], 0 if valid else 1)
                self.assertEqual(manifest["counts"]["errors"], 0)
                self.assertTrue((output / "result_one.json").exists())

    def test_all_saved_cases_conserve_parts_and_match_independent_safety_and_legacy(self):
        boxes = json.loads((ROOT / "box_research" / "box_db.json").read_text(encoding="utf-8"))
        lids = json.loads((ROOT / "box_research" / "lid_db.json").read_text(encoding="utf-8"))
        pallets = json.loads((ROOT / "box_research" / "pallet_db.json").read_text(encoding="utf-8"))
        for name, case in self.catalog["cases"]["test_cases"].items():
            with self.subTest(case=name):
                result = self.calculate(case)
                self.assert_quantities(result, case)
                independent = self.independently_validate(result)
                self.assertEqual(independent["is_pass"], result["summary"]["is_valid"],
                                 independent["violations"])
                original = json.loads(
                    (ROOT / "test_programmer" / "test_cases" / (name + ".json")).read_text(encoding="utf-8"))
                specs, rows = resolve_box_specs(original["box_list"], boxes, lids)
                baseline = Palletizer(specs, resolve_pallet_spec(original, pallets)).run(name, rows).to_dict()
                if baseline["summary"]["is_valid"]:
                    self.assertTrue(result["summary"]["is_valid"], result["summary"]["violations"])
                self.assertGreaterEqual(result["placed_boxes_count"], baseline["placed_boxes_count"])


if __name__ == "__main__":
    unittest.main()
