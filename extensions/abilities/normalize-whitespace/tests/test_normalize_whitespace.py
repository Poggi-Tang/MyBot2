import contextlib
import io
import tempfile
import unittest
from pathlib import Path
import sys

ABILITY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ABILITY_ROOT))
from scripts.normalize_whitespace import main, normalize


class NormalizeWhitespaceTests(unittest.TestCase):
    def test_collapses_mixed_whitespace_and_trims(self):
        self.assertEqual(normalize("  alpha\t beta\n\n gamma  "), "alpha beta gamma")

    def test_cli_reads_and_writes_parameterized_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.txt"
            target = root / "nested" / "result.txt"
            target.parent.mkdir()
            source.write_text("one   two\nthree", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["--input", str(source), "--output", str(target)])
            self.assertEqual(status, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "one two three")
            self.assertIn("normalized whitespace", output.getvalue())

    def test_missing_input_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.txt"
            target = Path(directory) / "result.txt"
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                status = main(["--input", str(missing), "--output", str(target)])
            self.assertEqual(status, 1)
            self.assertIn("error:", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
