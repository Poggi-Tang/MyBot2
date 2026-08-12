import json
import tempfile
import unittest
from pathlib import Path

from mybot_ui.extension_registry import ExtensionRegistry, ExtensionRegistryError


class ExtensionRegistryTests(unittest.TestCase):
    def test_mcp_import_enable_disable_and_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "servers.json"
            config.write_text(json.dumps({
                "mcpServers": {
                    "demo": {
                        "command": "demo.exe",
                        "args": ["serve"],
                        "env": {"MODE": "test"},
                    }
                }
            }), encoding="utf-8")
            registry = ExtensionRegistry(root)

            self.assertEqual(("demo",), registry.import_mcp(config))
            self.assertTrue(registry.mcp_enabled("demo"))
            registry.set_mcp_enabled("demo", False)
            self.assertFalse(registry.mcp_enabled("demo"))
            registry.remove_mcp("demo")
            self.assertFalse(any(item["id"] == "demo" for item in registry.list_mcps()))

    def test_builtin_mcp_can_be_disabled_but_not_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ExtensionRegistry(directory)
            registry.set_mcp_enabled("autowx", False)
            self.assertFalse(registry.mcp_enabled("autowx"))
            with self.assertRaisesRegex(ExtensionRegistryError, "只能禁用"):
                registry.remove_mcp("autowx")

    def test_skill_import_sync_disable_enable_and_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-skill"
            source.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: Demo skill\n---\n",
                encoding="utf-8",
            )
            registry = ExtensionRegistry(root / "project")

            self.assertEqual("demo-skill", registry.import_skill(source))
            mirror = registry.project_root / ".agents" / "skills" / "demo-skill"
            self.assertTrue((mirror / "SKILL.md").is_file())
            registry.set_skill_enabled("demo-skill", False)
            self.assertFalse(mirror.exists())
            registry.set_skill_enabled("demo-skill", True)
            self.assertTrue((mirror / "SKILL.md").is_file())
            registry.remove_skill("demo-skill")
            self.assertFalse(mirror.exists())
            self.assertEqual((), registry.list_skills())


if __name__ == "__main__":
    unittest.main()
