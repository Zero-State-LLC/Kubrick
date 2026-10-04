#!/usr/bin/env python3
"""Added em dashes fail the ratchet; lines already on the base do not."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import check_no_new_em_dash as check  # noqa: E402

EM = "\u2014"
DIFF = (
    "diff --git a/docs/a.md b/docs/a.md\n"
    "--- a/docs/a.md\n"
    "+++ b/docs/a.md\n"
    "@@ -3,0 +4,2 @@\n"
    f"+clean line\n"
    f"+bad {EM} line\n"
    "diff --git a/skills/kubrick/docs/a.md b/skills/kubrick/docs/a.md\n"
    "--- a/skills/kubrick/docs/a.md\n"
    "+++ b/skills/kubrick/docs/a.md\n"
    "@@ -3,0 +4 @@\n"
    f"+bad {EM} line\n"
    "diff --git a/x.py b/x.py\n"
    "--- a/x.py\n"
    "+++ b/x.py\n"
    "@@ -1 +1 @@\n"
    f"-old {EM} line\n"
    f"+++ added text {EM} that looks like a header\n"
    "@@ -9,0 +10 @@\n"
    f"+fixture {EM} # em-dash: allow\n"
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


def test_added_lines_track_paths_and_numbers() -> None:
    lines = check.added_lines(DIFF)
    assert ("docs/a.md", 5) in [(h.path, h.line) for h in lines]
    assert ("x.py", 1) in [(h.path, h.line) for h in lines]


def test_find_hits_skips_mirror_allow_and_removed_lines() -> None:
    hits = check.find_hits(DIFF)
    assert [(h.path, h.line) for h in hits] == [("docs/a.md", 5), ("x.py", 1)]


def test_git_repo_only_new_lines_fail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root, "init", "-q", "-b", "main")
        (root / "old.md").write_text(f"legacy {EM} line\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "base")
        _git(root, "checkout", "-q", "-b", "work")
        (root / "old.md").write_text(f"legacy {EM} line\nnew clean line\n", encoding="utf-8")
        _git(root, "commit", "-q", "-am", "clean")
        assert check.main(["--base", "main", "--root", str(root)]) == 0
        (root / "new.md").write_text(f"one\ntwo {EM} three\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "dash")
        hits = check.find_hits(check.git_diff("main", root))
        assert [(h.path, h.line) for h in hits] == [("new.md", 2)]
        assert check.main(["--base", "main", "--root", str(root)]) == 1


def test_missing_base_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root, "init", "-q", "-b", "main")
        (root / "a.md").write_text("a\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "base")
        assert check.main(["--base", "no-such-ref", "--root", str(root)]) == 2


def main() -> None:
    test_added_lines_track_paths_and_numbers()
    test_find_hits_skips_mirror_allow_and_removed_lines()
    test_git_repo_only_new_lines_fail()
    test_missing_base_fails_closed()
    print("em dash ratchet tests: PASS")


if __name__ == "__main__":
    main()
