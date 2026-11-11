import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from box_research.catalog_store import (
    FILES, initialize_catalog, load_catalog,
    prepare_cases, preview_model_rename, rename_model, save_catalog, validate_catalog,
)
from box_research.database_validation import (
    STANDARD_PALLET, STANDARD_PALLET_ID, validate_part_case_references,
)
from box_research.preview_migration import build_preview


class CatalogFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = self.root / "box_research"
        self.db.mkdir()
        case_dir = self.root / "test_programmer" / "test_cases"
        case_dir.mkdir(parents=True)
        model = {
            "id": "NP22C", "type": "NON_TP", "length": 610, "width": 370, "height": 156,
            "fitting_depth": 7, "rib_thickness": 18, "module_ratio": None,
            "compatible_lids": ["サンボックス＃22B"],
        }
        lids = {
            "無蓋": {"id": "無蓋", "type": "NONE", "fit_type": "なし",
                   "length": 0, "width": 0, "thickness": 0},
            "サンボックス＃22B": {
                "id": "サンボックス＃22B", "type": "OTHER", "fit_type": "内嵌め",
                "length": 606, "width": 369, "thickness": 15,
            },
        }
        self.write_json(self.db / "box_db.json", {"NP22C": model})
        self.write_json(self.db / "lid_db.json", lids)
        self.write_json(self.db / "pallet_db.json", {"pallets": {STANDARD_PALLET_ID: STANDARD_PALLET}})
        self.write_json(case_dir / "case.json", {
            "supplier_name": "オティックス", "name": "case", "description": "Original case",
            "pallet_id": STANDARD_PALLET_ID,
            "pallet": {"max_x_span": 1360, "max_y_span": 1100, "max_height": 1200},
            "box_list": [{"box_id": "NP22C", "count": 10, "lid_id": "サンボックス＃22B"}],
        })
        with (self.db / "box_list.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["仕入先名", "品番", "箱種", "型式"])
            writer.writerow(["オティックス", "00001", "NP22C", "ｻﾝﾎﾞｯｸｽ＃22B"])
        self.preview = self.root / "approved.json"
        self.write_json(self.preview, build_preview(self.root))
        self.data = initialize_catalog(self.root, self.preview)

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def snapshot(self):
        return {path.name: path.read_bytes() for path in (self.db / "catalog").glob("*.json")}


class CatalogStoreTest(CatalogFixture, unittest.TestCase):
    def test_initialization_and_round_trip_preserve_sources(self):
        saved, revision = load_catalog(self.root)
        self.assertEqual(saved, self.data)
        for path, digest in saved["migration"]["source_sha256"].items():
            self.assertEqual(hashlib.sha256((self.root / path).read_bytes()).hexdigest(), digest)
        self.assertEqual(saved["parts"]["00001"]["box_model_id"], "サンボックス#22H")
        self.assertEqual(saved["parts"]["00001"]["lid_id"], "サンボックス#22Bフタ")
        self.assertEqual(save_catalog(self.root, saved, revision), revision)
        self.assertEqual(set(self.snapshot()), set(FILES.values()))

    def test_initialization_refuses_overwrite(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "上書き"):
            initialize_catalog(self.root, self.preview)
        self.assertEqual(self.snapshot(), before)

    def test_edited_approval_is_rejected(self):
        approved = json.loads(self.preview.read_text(encoding="utf-8"))
        approved["parts"][0]["lid_id"] = "無蓋"
        self.write_json(self.preview, approved)
        with self.assertRaisesRegex(ValueError, "移行案が異なります"):
            initialize_catalog(self.root, self.preview)

    def test_normalization_at_save_updates_references(self):
        data, revision = load_catalog(self.root)
        model = data["models"].pop("サンボックス#22H")
        model["id"] = "ｻﾝﾎﾞｯｸｽ＃２２Ｈ"
        data["models"][model["id"]] = model
        data["parts"]["00001"]["box_model_id"] = model["id"]
        save_catalog(self.root, data, revision)
        saved, _ = load_catalog(self.root)
        self.assertIn("サンボックス#22H", saved["models"])
        self.assertEqual(saved["parts"]["00001"]["box_model_id"], "サンボックス#22H")

    def test_collisions_rejected_before_save(self):
        data, revision = load_catalog(self.root)
        data["models"]["ｻﾝﾎﾞｯｸｽ＃２２Ｈ"] = copy.deepcopy(data["models"]["サンボックス#22H"])
        data["models"]["ｻﾝﾎﾞｯｸｽ＃２２Ｈ"]["id"] = "ｻﾝﾎﾞｯｸｽ＃２２Ｈ"
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "重複"):
            save_catalog(self.root, data, revision)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_dimensions_rejected(self):
        for field in ("length", "width", "height", "fitting_depth", "rib_thickness"):
            for value in (True, "1", None, -1, float("nan"), float("inf")):
                with self.subTest(field=field, value=value):
                    data = copy.deepcopy(self.data)
                    data["models"]["サンボックス#22H"][field] = value
                    with self.assertRaises(ValueError):
                        validate_catalog(data)
        for update in ({"length": 300}, {"fitting_depth": 156},
                       {"top_support_points": True}, {"top_support_points": 6}):
            data = copy.deepcopy(self.data)
            data["models"]["サンボックス#22H"].update(update)
            with self.assertRaises(ValueError):
                validate_catalog(data)

    def test_invalid_lids_and_unknown_references_rejected(self):
        updates = (
            ("lids", "無蓋", {"thickness": 1}),
            ("lids", "サンボックス#22Bフタ", {"fit_type": "なし"}),
            ("parts", "00001", {"box_model_id": "UNKNOWN"}),
            ("parts", "00001", {"lid_id": "UNKNOWN"}),
            ("models", "サンボックス#22H", {"compatible_lids": []}),
            ("models", "サンボックス#22H", {"compatible_lids": ["UNKNOWN"]}),
        )
        for collection, key, update in updates:
            with self.subTest(update=update):
                data = copy.deepcopy(self.data)
                data[collection][key].update(update)
                with self.assertRaises(ValueError):
                    validate_catalog(data)

    def test_used_part_and_model_deletion_is_rejected(self):
        for collection, key in (("parts", "00001"), ("models", "サンボックス#22H")):
            data = copy.deepcopy(self.data)
            data["parts"]["00002"] = dict(data["parts"]["00001"], id="00002")
            del data[collection][key]
            with self.assertRaises(ValueError):
                validate_catalog(data)

    def test_case_supplier_count_and_fixed_lid(self):
        valid = {"supplier_name": "オティックス",
                 "box_list": [{"part_number": "00001", "count": 1}]}
        validate_part_case_references(valid, self.data["parts"])
        invalid = copy.deepcopy(valid)
        invalid["supplier_name"] = "別の仕入先"
        with self.assertRaises(ValueError):
            validate_part_case_references(invalid, self.data["parts"])
        for update in ({"part_number": "UNKNOWN"}, {"count": True}, {"count": 0},
                       {"count": 1.5}, {"count": 501}, {"lid_id": "無蓋"}, {"box_id": "NP22C"}):
            invalid = copy.deepcopy(valid)
            invalid["box_list"][0].update(update)
            with self.subTest(update=update):
                with self.assertRaises(ValueError):
                    validate_part_case_references(invalid, self.data["parts"])

    def test_rename_requires_confirmation_and_preserves_history(self):
        before = self.snapshot()
        plan = preview_model_rename(self.root, "サンボックス#22H", "新しい箱")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(plan["affected_parts"], ["00001"])
        self.assertEqual(plan["affected_cases"], ["case.json"])
        with self.assertRaisesRegex(ValueError, "確認番号"):
            rename_model(self.root, plan["old_name"], plan["new_name"], "invalid")
        rename_model(self.root, plan["old_name"], plan["new_name"], plan["confirmation"])
        second = preview_model_rename(self.root, "新しい箱", "新しい箱2")
        rename_model(self.root, second["old_name"], second["new_name"], second["confirmation"])
        saved, _ = load_catalog(self.root)
        self.assertEqual(saved["parts"]["00001"]["box_model_id"], "新しい箱2")
        self.assertEqual(saved["migration"]["legacy_model_mapping"]["NP22C"], "新しい箱2")
        self.assertEqual(saved["migration"]["model_name_history"], {
            "サンボックス#22H": "新しい箱2", "新しい箱": "新しい箱2",
        })
        for name in ("サンボックス#22H", "NS80858", "NP22C", "　"):
            with self.assertRaises(ValueError):
                preview_model_rename(self.root, "新しい箱2", name)

    def test_stale_plan_and_stale_save_are_rejected(self):
        plan = preview_model_rename(self.root, "サンボックス#22H", "新しい箱")
        data, revision = load_catalog(self.root)
        data["models"]["サンボックス#22H"]["description"] = "changed"
        save_catalog(self.root, data, revision)
        with self.assertRaisesRegex(ValueError, "再確認"):
            rename_model(self.root, plan["old_name"], plan["new_name"], plan["confirmation"])
        with self.assertRaisesRegex(ValueError, "再確認"):
            save_catalog(self.root, data, revision)

    def test_source_changes_and_added_cases_are_rejected(self):
        source = self.db / "box_list.csv"
        original = source.read_bytes()
        source.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "元データ"):
            load_catalog(self.root)
        source.write_bytes(original)
        self.write_json(self.root / "test_programmer" / "test_cases" / "extra.json", {})
        with self.assertRaisesRegex(ValueError, "追加"):
            load_catalog(self.root)

    def test_lock_prevents_concurrent_save(self):
        data, revision = load_catalog(self.root)
        lock = self.db / "catalog" / ".save.lock"
        lock.write_text("test", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "処理中"):
            save_catalog(self.root, data, revision)
        self.assertTrue(lock.exists())

    def test_partial_save_failure_restores_all_files(self):
        data, revision = load_catalog(self.root)
        before = self.snapshot()
        data["models"]["サンボックス#22H"]["description"] = "changed"
        data["parts"]["00002"] = dict(data["parts"]["00001"], id="00002")
        replace = os.replace
        calls = []

        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError("test replacement failure")
            return replace(source, target)

        with patch("box_research.catalog_store.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "test replacement failure"):
                save_catalog(self.root, data, revision)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(len(list((self.db / "catalog").iterdir())), 4)

    def test_failed_initial_save_removes_new_partial_files(self):
        directory = self.db / "catalog"
        for path in directory.iterdir():
            path.unlink()
        replace = os.replace
        calls = []

        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError("initial failure")
            return replace(source, target)

        with patch("box_research.catalog_store.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "initial failure"):
                initialize_catalog(self.root, self.preview)
        self.assertEqual(list(directory.iterdir()), [])

    def test_rollback_failure_retains_recovery_copy(self):
        data, revision = load_catalog(self.root)
        replace = os.replace
        calls = []

        def fail_save_and_restore(source, target):
            calls.append(target)
            if len(calls) >= 2:
                raise OSError("test disk failure")
            return replace(source, target)

        with patch("box_research.catalog_store.os.replace", side_effect=fail_save_and_restore):
            with self.assertRaisesRegex(OSError, "復旧用コピー"):
                save_catalog(self.root, data, revision)
        self.assertTrue(list((self.db / "catalog").glob(".catalog-*.tmp")))
        self.assertFalse((self.db / "catalog" / ".save.lock").exists())

    def test_duplicate_json_keys_are_rejected_on_load(self):
        path = self.db / "catalog" / "box_type_db.json"
        path.write_text('{"same": {}, "same": {}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "重複"):
            load_catalog(self.root)

    def test_prepare_cases_preserves_originals_and_adoption(self):
        approval_path = self.root / "test_programmer" / "test_case_approval.json"
        self.write_json(approval_path, {"case": False})
        before = {path: path.read_bytes() for path in
                  (self.root / "test_programmer").rglob("*.json")}
        bundle = prepare_cases(self.root)
        self.assertEqual(bundle["test_cases"]["case"]["box_list"],
                         [{"part_number": "00001", "count": 10}])
        self.assertFalse(bundle["approval_state"]["case"])
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertEqual(len(self.snapshot()), 5)
        with self.assertRaisesRegex(ValueError, "登録済み"):
            prepare_cases(self.root)

    def test_staged_case_edits_can_change_assigned_part_and_delete_cases(self):
        prepare_cases(self.root)
        data, revision = load_catalog(self.root)
        data["parts"]["00002"] = dict(data["parts"]["00001"], id="00002")
        data["cases"]["test_cases"]["case"]["box_list"][0]["part_number"] = "00002"
        del data["parts"]["00001"]
        save_catalog(self.root, data, revision)
        saved, revision = load_catalog(self.root)
        self.assertNotIn("00001", saved["parts"])
        saved["cases"]["test_cases"].clear()
        saved["cases"]["approval_state"].clear()
        save_catalog(self.root, saved, revision)
        self.assertFalse(load_catalog(self.root)[0]["cases"]["test_cases"])

    def test_staged_case_validation_and_omission_guard(self):
        prepare_cases(self.root)
        data, revision = load_catalog(self.root)
        before = self.snapshot()
        for update in (
            {"pallet_id": "UNKNOWN"},
            {"pallet": {"max_x_span": 0, "max_y_span": 1000, "max_height": 1200}},
            {"pallet": {"max_x_span": 900, "max_y_span": 1000, "max_height": 1200}},
            {"description": ""},
        ):
            draft = copy.deepcopy(data)
            draft["cases"]["test_cases"]["case"].update(update)
            with self.assertRaises(ValueError):
                save_catalog(self.root, draft, revision)
        draft = copy.deepcopy(data)
        del draft["cases"]
        with self.assertRaisesRegex(ValueError, "省略"):
            save_catalog(self.root, draft, revision)
        self.assertEqual(self.snapshot(), before)

    def test_rename_impact_uses_live_staged_cases(self):
        prepare_cases(self.root)
        data, revision = load_catalog(self.root)
        data["cases"]["test_cases"]["case2"] = dict(
            data["cases"]["test_cases"]["case"], name="case2")
        data["cases"]["approval_state"]["case2"] = True
        save_catalog(self.root, data, revision)
        plan = preview_model_rename(self.root, "サンボックス#22H", "新モデル")
        self.assertEqual(plan["affected_cases"], ["case.json", "case2.json"])
        rename_model(self.root, plan["old_name"], plan["new_name"], plan["confirmation"])
        saved, _ = load_catalog(self.root)
        self.assertEqual(saved["cases"]["test_cases"]["case"]["box_list"][0]["part_number"], "00001")
        self.assertEqual(saved["parts"]["00001"]["box_model_id"], "新モデル")


if __name__ == "__main__":
    unittest.main()
