"""Current distribution metadata must match the unchanged root license."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LicenseMetadata(unittest.TestCase):
    def test_current_distribution_metadata(self):
        self.assertIn("Zero State Proprietary License", (ROOT / "LICENSE").read_text())
        files = [ROOT / "SKILL.md", ROOT / "README.md"]
        files += list((ROOT / "skills").glob("*/SKILL.md"))
        files += list((ROOT / "skills").glob("*/README.md"))
        files += [
            p
            for p in [
                ROOT / "manifest.json",
                ROOT / "references/manifest.json",
                ROOT / "hyperlex.manifest.yaml",
                ROOT / "pyproject.toml",
            ]
            if p.exists()
        ]
        for p in files:
            with self.subTest(path=str(p)):
                self.assertNotRegex(p.read_text(), r"\bMIT\b")
        self.assertIn(
            "license: LicenseRef-Zero-State-Proprietary-1.0", (ROOT / "SKILL.md").read_text()
        )


if __name__ == "__main__":
    unittest.main()
