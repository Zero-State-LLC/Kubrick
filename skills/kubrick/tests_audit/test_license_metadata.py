"""Distribution metadata must carry the MIT license policy."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LicenseMetadata(unittest.TestCase):
    def test_current_distribution_metadata(self):
        license_text = (ROOT / "LICENSE").read_text()
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 Zero State LLC", license_text)
        self.assertIn("license: MIT", (ROOT / "SKILL.md").read_text())

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
                text = p.read_text()
                self.assertNotIn("Zero State Proprietary", text)
                self.assertNotIn("LicenseRef-Zero-State-Proprietary", text)


if __name__ == "__main__":
    unittest.main()
