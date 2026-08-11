import json
import tempfile
import unittest
from pathlib import Path

from mybot_ui.extension_abilities import AbilityValidationError, ExtensionAbilityStore, _directory_digest


class ExtensionAbilityStoreTests(unittest.TestCase):
    def _candidate(self, root: Path, *, secret: str = "") -> Path:
        store = ExtensionAbilityStore(root / "extensions")
        candidate = store.candidate_path("task-1")
        (candidate / "scripts").mkdir(parents=True)
        (candidate / "tests").mkdir()
        (candidate / "manifest.json").write_text(json.dumps({
            "reusable": True,
            "id": "normalize-text",
            "name": "规范化文本",
            "description": "统一清理文本空白并输出稳定结果",
            "triggers": ["清理文本", "规范空白"],
        }, ensure_ascii=False), encoding="utf-8")
        (candidate / "recipe.md").write_text("运行 scripts/normalize.py。" + secret, encoding="utf-8")
        (candidate / "SKILL.md").write_text(
            "---\nname: normalize-text\ndescription: Normalize text whitespace.\n---\n\n"
            "Use the parameterized script and verify the output with the bundled tests.\n",
            encoding="utf-8",
        )
        (candidate / "scripts" / "normalize.py").write_text(
            "def normalize(value):\n    return ' '.join(value.split())\n",
            encoding="utf-8",
        )
        (candidate / "tests" / "test_normalize.py").write_text(
            "import sys, unittest\nfrom pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))\n"
            "from normalize import normalize\n"
            "class T(unittest.TestCase):\n"
            "    def test_spaces(self): self.assertEqual('a b', normalize('a  b'))\n",
            encoding="utf-8",
        )
        return candidate

    def test_promotes_verified_candidate_and_matches_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ExtensionAbilityStore(root / "extensions")
            item = store.promote_candidate(self._candidate(root))

            self.assertEqual("normalize-text", item["id"])
            matches = store.matching("帮我清理文本中的多余空白")
            self.assertEqual("normalize-text", matches[0].ability_id)
            self.assertIn("normalize.py", store.matching_context("规范空白"))
            self.assertEqual((), store.matching("return task count and ability count"))
            store.record_usage(("normalize-text",))
            published = store.list_abilities()[0]
            self.assertEqual(1, published["usage_count"])
            self.assertIn("last_used_at", published)

            published["name"] = "changed outside store"
            self.assertEqual("规范化文本", store.list_abilities()[0]["name"])

    def test_rejects_secret_or_conversation_specific_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ExtensionAbilityStore(root / "extensions")
            candidate = self._candidate(root, secret=" sk-exampleSecret123456")
            with self.assertRaises(AbilityValidationError):
                store.promote_candidate(candidate)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ExtensionAbilityStore(root / "extensions")
            candidate = self._candidate(root, secret=" 芝士圆子")
            with self.assertRaises(AbilityValidationError):
                store.promote_candidate(candidate, forbidden_terms=("芝士圆子",))

    def test_digest_ignores_python_cache_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "script.py").write_text("print('ok')\n", encoding="utf-8")
            before = _directory_digest(root)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "script.cpython-313.pyc").write_bytes(b"transient")
            self.assertEqual(before, _directory_digest(root))


if __name__ == "__main__":
    unittest.main()
