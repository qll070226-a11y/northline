import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "controlled_pilot_builder", ROOT / "experiments" / "build_controlled_pilot.py"
)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class ControlledPilotBuilderTests(unittest.TestCase):
    def test_write_text_files_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsafe blueprint path"):
                BUILDER.write_text_files(Path(directory), {"../outside.py": "bad"})

    def test_reset_requires_direct_child_and_explicit_force(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "generated"
            BUILDER.reset_generated_directory(target, parent, False)
            with self.assertRaises(FileExistsError):
                BUILDER.reset_generated_directory(target, parent, False)
            BUILDER.reset_generated_directory(target, parent, True)
            self.assertTrue(target.is_dir())

    def test_tree_hash_is_order_independent(self):
        self.assertEqual(
            BUILDER.tree_hash({"a": "one", "b": "two"}),
            BUILDER.tree_hash({"b": "two", "a": "one"}),
        )


if __name__ == "__main__":
    unittest.main()
