import unittest
from pathlib import Path


class InstallerCliPolicyTests(unittest.TestCase):
    def test_cli_is_only_installed_from_the_application(self):
        root = Path(__file__).resolve().parents[1]
        installer = (root / "installer" / "MyBot2.iss").read_text(encoding="utf-8")
        build_script = (root / "scripts" / "build-installer.ps1").read_text(encoding="utf-8")
        workflow = (
            root / ".github" / "workflows" / "release-installer.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn('Name: "codex"', installer)
        self.assertNotIn("runtime\\codex", installer)
        self.assertNotIn("codex_extension", installer)
        self.assertNotIn("IncludeCodex", build_script)
        self.assertNotIn("IncludeCodex", workflow)


if __name__ == "__main__":
    unittest.main()
