import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tester import run_tests


class HandOrderRunnerTests(unittest.TestCase):
    def test_equipment_arguments_and_failed_cli_do_not_reuse_old_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case.json"
            case.write_text("{}", encoding="utf-8")
            results = root / "results"
            results.mkdir()
            output = results / "result_case.json"
            output.write_text(json.dumps({"summary": {"is_valid": True}}), encoding="utf-8")
            before = output.read_bytes()
            log = io.StringIO()
            with patch.object(run_tests, "TEST_CASES_DIR", str(root)), \
                    patch.object(run_tests, "RESULTS_DIR", str(results)), \
                    patch.object(run_tests, "load_approval_state", return_value=None), \
                    patch.object(run_tests.subprocess, "run", return_value=subprocess.CompletedProcess(
                        [], 1, stdout="", stderr="HandSequenceError: blocked")) as execute, \
                    contextlib.redirect_stdout(log):
                code = run_tests.run_all_tests("equipment.json", "equipment-id")
            self.assertEqual(code, 1)
            command = execute.call_args[0][0]
            self.assertEqual(command[-4:], ["--hand-profiles", "equipment.json",
                                           "--hand-profile-id", "equipment-id"])
            self.assertEqual(output.read_bytes(), before)
            self.assertIn("HandSequenceError", log.getvalue())
            self.assertNotIn("PASS", log.getvalue())


if __name__ == "__main__":
    unittest.main()
