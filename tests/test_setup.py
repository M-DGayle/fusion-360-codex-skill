import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("setup_bridge", Path(__file__).parents[1] / "scripts" / "setup_bridge.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_config_uses_supplied_roots_including_spaces(self):
        root = Path("example user") / "skills" / "fusion-bridge"
        state = Path("private runtime")
        config = setup.config_for(root, state)["mcpServers"]["fusion"]
        self.assertEqual(config["args"], [str(root / "server.py")])
        self.assertEqual(config["command"], str(state / "venv" / "Scripts" / "python.exe"))

    def test_config_creation_and_idempotent_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".mcp.json"
            config = setup.config_for(Path(directory), Path(directory) / "state")
            setup.write_config(target, config)
            original = target.read_bytes()
            setup.write_config(target, config)
            self.assertEqual(original, target.read_bytes())
            self.assertEqual(json.loads(original), config)

    def test_conflicting_config_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / ".mcp.json"
            setup.write_config(target, {"existing": True})
            with self.assertRaisesRegex(RuntimeError, "differs"):
                setup.write_config(target, {"replacement": True})
            self.assertEqual(json.loads(target.read_text()), {"existing": True})
            setup.write_config(target, {"replacement": True}, replace=True)
            self.assertEqual(json.loads(target.read_text()), {"replacement": True})


if __name__ == "__main__":
    unittest.main()
