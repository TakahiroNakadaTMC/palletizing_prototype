import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from box_research.catalog_store import (
    FILES, load_catalog, preview_model_rename, rename_model, save_catalog, validate_catalog,
)
from box_research.database_validation import STANDARD_PALLET, STANDARD_PALLET_ID
from box_research.skid_catalog import skid_snapshot


class CatalogFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog_dir = self.root / "box_research" / "catalog"
        self.catalog_dir.mkdir(parents=True)
        self.pallet_path = self.root / "box_research" / "pallet_db.json"
        self.model_id = "MODEL-A"
        self.lid_id = "LID-A"
        self.part_id = "00001"
        self.data = {
            "suppliers": {"0001": {"id": "0001", "supplier_name": "Supplier A"}},
            "parts": {
                self.part_id: {
                    "id": self.part_id, "supplier_name": "Supplier A",
                    "box_name": "Operational box", "box_model_id": self.model_id,
                    "lid_id": self.lid_id,
                }
            },
            "models": {
                self.model_id: {
                    "id": self.model_id, "type": "NON_TP", "length": 610,
                    "width": 370, "height": 156, "fitting_depth": 7,
                    "rib_thickness": 18, "module_ratio": None,
                    "top_support_points": 4, "compatible_lids": [self.lid_id],
                    "description": "Fixture model",
                }
            },
            "lids": {
                "NO-LID": {
                    "id": "NO-LID", "type": "NONE", "fit_type": "なし",
                    "length": 0, "width": 0, "thickness": 0,
                },
                self.lid_id: {
                    "id": self.lid_id, "type": "OTHER", "fit_type": "内嵌め",
                    "length": 606, "width": 369, "thickness": 15,
                },
            },
            "migration": {
                "schema_version": 1, "phase": "phase5_ready",
                "source_sha256": {
                    "box_research\\box_db.json": "obsolete-hash",
                    "test_programmer\\test_cases\\removed.json": "obsolete-hash",
                },
                "legacy_model_mapping": {"OLD-MODEL": self.model_id},
                "model_name_history": {},
                "case_assignments": [{
                    "case_file": "removed.json", "row": 1,
                    "part_number": "REMOVED", "count": 99,
                }],
                "approved_changes": [],
            },
            "skids": {
                "0001AA": {
                    "id": "0001AA", "supplier_name": "Supplier A",
                    "pallet_id": STANDARD_PALLET_ID,
                    "pallet": {"max_x_span": 1360, "max_y_span": 1100, "max_height": 1200},
                    "part_numbers": [self.part_id], "updated_at": "", "history": [],
                },
            },
            "cases": {
                "schema_version": 2,
                "test_cases": {
                    "case": {
                        "name": "case", "description": "Fixture case",
                        "supplier_name": "Supplier A", "skid_id": "0001AA",
                        "box_list": [{"part_number": self.part_id, "count": 10}],
                    }
                },
                "approval_state": {"case": True},
            },
            "pallets": {
                "pallets": {
                    STANDARD_PALLET_ID: copy.deepcopy(STANDARD_PALLET),
                    "PALLET-A": {
                        "id": "PALLET-A", "model": "Pallet A", "length": 1200,
                        "width": 1000, "height": 130, "suppliers": ["Supplier A"],
                    },
                }
            },
        }
        skid = self.data["skids"]["0001AA"]
        skid["updated_at"] = "2026-11-12T00:00:00+09:00"
        skid["history"] = [dict(updated_at=skid["updated_at"], before=None,
                                after=skid_snapshot(skid), affected_cases=["case"])]
        for key, filename in FILES.items():
            self.write_json(self.catalog_dir / filename, self.data[key])
        self.write_json(self.catalog_dir / "test_cases.json", self.data["cases"])
        self.write_json(self.pallet_path, self.data["pallets"])
        self.data, self.revision = load_catalog(self.root)

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def snapshot(self):
        return {
            path.relative_to(self.root): path.read_bytes()
            for path in [*self.catalog_dir.glob("*.json"), self.pallet_path]
        }


class CatalogStoreTest(CatalogFixture, unittest.TestCase):
    def test_load_and_edit_do_not_require_any_legacy_sources(self):
        self.assertFalse((self.root / "box_research" / "box_db.json").exists())
        self.assertFalse((self.root / "box_research" / "lid_db.json").exists())
        self.assertFalse((self.root / "box_research" / "box_list.csv").exists())
        self.assertFalse((self.root / "test_programmer" / "test_cases").exists())
        self.assertEqual(self.data["migration"]["legacy_model_mapping"], {"OLD-MODEL": self.model_id})
        draft = copy.deepcopy(self.data)
        draft["parts"][self.part_id]["box_name"] = "Updated name"
        save_catalog(self.root, draft, self.revision)
        saved, _ = load_catalog(self.root)
        self.assertEqual(saved["parts"][self.part_id]["box_name"], "Updated name")
        self.assertEqual(saved["migration"]["source_sha256"], self.data["migration"]["source_sha256"])

    def test_revision_tracks_pallet_database_and_rejects_stale_saves(self):
        stale = copy.deepcopy(self.data)
        pallets = copy.deepcopy(self.data["pallets"])
        pallets["pallets"]["PALLET-A"]["height"] += 1
        self.write_json(self.pallet_path, pallets)
        with self.assertRaisesRegex(ValueError, "再確認"):
            save_catalog(self.root, stale, self.revision)

    def test_revision_and_loading_treat_lf_and_crlf_as_equivalent(self):
        before, revision = load_catalog(self.root)
        paths = [*self.catalog_dir.glob("*.json"), self.pallet_path]
        for path in paths:
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        loaded, crlf_revision = load_catalog(self.root)
        self.assertEqual(loaded, before)
        self.assertEqual(crlf_revision, revision)
        self.assertEqual(save_catalog(self.root, loaded, revision), revision)

    def test_catalog_crud_normalizes_ids_and_preserves_values(self):
        draft = copy.deepcopy(self.data)
        draft["parts"]["００００２"] = dict(draft["parts"][self.part_id], id="００００２")
        save_catalog(self.root, draft, self.revision)
        saved, revision = load_catalog(self.root)
        self.assertIn("00002", saved["parts"])
        self.assertNotIn("００００２", saved["parts"])
        del saved["parts"]["00002"]
        save_catalog(self.root, saved, revision)
        self.assertNotIn("00002", load_catalog(self.root)[0]["parts"])

    def test_invalid_dimensions_and_unknown_references_are_rejected(self):
        for field in ("length", "width", "height", "fitting_depth", "rib_thickness"):
            for value in (True, "1", None, -1, float("nan"), float("inf")):
                draft = copy.deepcopy(self.data)
                draft["models"][self.model_id][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_catalog(draft)
        updates = (
            ("parts", self.part_id, {"lid_id": "UNKNOWN"}),
            ("parts", self.part_id, {"box_model_id": "UNKNOWN"}),
            ("models", self.model_id, {"compatible_lids": ["UNKNOWN"]}),
            ("cases", "test_cases", None),
        )
        for collection, key, update in updates[:-1]:
            draft = copy.deepcopy(self.data)
            draft[collection][key].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_catalog(draft)
        draft = copy.deepcopy(self.data)
        draft["cases"]["test_cases"]["case"]["box_list"][0]["count"] = 501
        with self.assertRaises(ValueError):
            validate_catalog(draft)

    def test_used_part_model_lid_and_pallet_cannot_be_deleted(self):
        for collection, key in (
            ("parts", self.part_id), ("models", self.model_id), ("lids", self.lid_id),
        ):
            draft = copy.deepcopy(self.data)
            del draft[collection][key]
            with self.subTest(collection=collection), self.assertRaises(ValueError):
                validate_catalog(draft)
        draft = copy.deepcopy(self.data)
        del draft["pallets"]["pallets"][STANDARD_PALLET_ID]
        with self.assertRaises(ValueError):
            validate_catalog(draft)

    def test_legacy_mapping_is_audit_only_but_model_history_is_safe(self):
        draft = copy.deepcopy(self.data)
        draft["models"]["UNUSED-MODEL"] = dict(draft["models"][self.model_id], id="UNUSED-MODEL")
        draft["migration"]["legacy_model_mapping"]["OLD-MODEL"] = "UNUSED-MODEL"
        validate_catalog(draft)
        del draft["models"]["UNUSED-MODEL"]
        validate_catalog(draft)
        self.assertEqual(draft["migration"]["legacy_model_mapping"]["OLD-MODEL"], "UNUSED-MODEL")
        draft["migration"]["model_name_history"]["OLD-NAME"] = "DELETED-MODEL"
        with self.assertRaises(ValueError):
            validate_catalog(draft)

    def test_confirmed_rename_tracks_current_references_and_history(self):
        before = self.snapshot()
        plan = preview_model_rename(self.root, self.model_id, "MODEL-B")
        self.assertEqual(plan["affected_parts"], [self.part_id])
        self.assertEqual(plan["affected_cases"], ["case.json"])
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(ValueError, "確認番号"):
            rename_model(self.root, self.model_id, "MODEL-B", "invalid")
        rename_model(self.root, self.model_id, "MODEL-B", plan["confirmation"])
        saved, _ = load_catalog(self.root)
        self.assertEqual(saved["parts"][self.part_id]["box_model_id"], "MODEL-B")
        self.assertEqual(saved["migration"]["legacy_model_mapping"]["OLD-MODEL"], self.model_id)
        self.assertEqual(saved["migration"]["model_name_history"], {self.model_id: "MODEL-B"})
        with self.assertRaisesRegex(ValueError, "旧名称"):
            preview_model_rename(self.root, "MODEL-B", self.model_id)
        next_plan = preview_model_rename(self.root, "MODEL-B", "MODEL-C")
        rename_model(self.root, "MODEL-B", "MODEL-C", next_plan["confirmation"])
        saved, _ = load_catalog(self.root)
        self.assertEqual(saved["migration"]["model_name_history"],
                         {self.model_id: "MODEL-C", "MODEL-B": "MODEL-C"})

    def test_normal_save_protects_history_and_used_model_transitions(self):
        before = self.snapshot()
        draft = copy.deepcopy(self.data)
        draft["migration"]["model_name_history"]["OLD-NAME"] = self.model_id
        with self.assertRaisesRegex(ValueError, "履歴"):
            save_catalog(self.root, draft, self.revision)
        self.assertEqual(self.snapshot(), before)

        draft = copy.deepcopy(self.data)
        model = draft["models"].pop(self.model_id)
        model["id"] = "MODEL-B"
        draft["models"]["MODEL-B"] = model
        draft["parts"][self.part_id]["box_model_id"] = "MODEL-B"
        with self.assertRaisesRegex(ValueError, "名前変更"):
            save_catalog(self.root, draft, self.revision)
        self.assertEqual(self.snapshot(), before)

        draft["parts"]["00002"] = dict(draft["parts"].pop(self.part_id), id="00002")
        draft["cases"]["test_cases"].clear()
        draft["cases"]["approval_state"].clear()
        with self.assertRaisesRegex(ValueError, "名前変更"):
            save_catalog(self.root, draft, self.revision)
        self.assertEqual(self.snapshot(), before)

    def test_normal_save_can_add_and_delete_unused_models(self):
        draft = copy.deepcopy(self.data)
        draft["models"]["UNUSED"] = dict(draft["models"][self.model_id], id="UNUSED")
        save_catalog(self.root, draft, self.revision)
        draft, revision = load_catalog(self.root)
        del draft["models"]["UNUSED"]
        draft["models"]["NEW"] = dict(draft["models"][self.model_id], id="NEW")
        save_catalog(self.root, draft, revision)
        saved, _ = load_catalog(self.root)
        self.assertNotIn("UNUSED", saved["models"])
        self.assertIn("NEW", saved["models"])

    def test_stale_rename_plan_and_stale_catalog_save_are_rejected(self):
        plan = preview_model_rename(self.root, self.model_id, "MODEL-B")
        draft = copy.deepcopy(self.data)
        draft["models"][self.model_id]["description"] = "changed"
        save_catalog(self.root, draft, self.revision)
        with self.assertRaisesRegex(ValueError, "再確認"):
            rename_model(self.root, plan["old_name"], plan["new_name"], plan["confirmation"])

    def test_lock_prevents_concurrent_save(self):
        lock = self.catalog_dir / ".save.lock"
        lock.write_text("test", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "処理中"):
            save_catalog(self.root, self.data, self.revision)
        self.assertTrue(lock.exists())

    def test_partial_save_failure_restores_catalog_and_pallet(self):
        before = self.snapshot()
        draft = copy.deepcopy(self.data)
        draft["models"][self.model_id]["description"] = "changed"
        draft["pallets"]["pallets"]["PALLET-A"]["height"] += 1
        replace = os.replace
        calls = []

        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError("test replacement failure")
            return replace(source, target)

        with patch("box_research.catalog_store.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "test replacement failure"):
                save_catalog(self.root, draft, self.revision)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.catalog_dir / ".save.lock").exists())


if __name__ == "__main__":
    unittest.main()
