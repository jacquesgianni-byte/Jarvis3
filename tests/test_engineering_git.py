"""
Genesis-016 Sprint 002 — Git Repository Awareness test battery.

Tests that Jarvis can observe Git state without modifying anything.
Every test is read-only. No git write commands are issued anywhere
in this suite.

Runs standalone: python tests/test_engineering_git.py
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.git.reader import GitReader
from core.engineering.git.models import GitStatus, CommitInfo
from core.engineering.coordinator import EngineeringCoordinator

passed = 0
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


print("\n[1] Git availability")
reader = GitReader(PROJECT_ROOT)
status = reader.status()
check("GitReader instantiates", reader is not None)
check("status() returns GitStatus", isinstance(status, GitStatus))
check("git is available on this machine", status.available)
if not status.available:
    print(f"    WARNING: git not available — {status.error}")
    print(f"    Remaining tests require git. Skipping.")
    print(f"\n{'='*60}")
    print(f"GENESIS-016 SPRINT 002: {passed} CHECKS PASS (git unavailable)")
    print(f"{'='*60}")
    sys.exit(0)


print("\n[2] Repository detection")
check("repository root is non-empty", bool(status.root))
check("repository root exists on disk", Path(status.root).exists())
check("project root detected correctly",
      str(PROJECT_ROOT) in status.root or status.root in str(PROJECT_ROOT))


print("\n[3] Branch detection")
check("branch name is non-empty", bool(status.branch))
check("branch name is not 'unknown'", status.branch != "unknown")
branch = reader.current_branch()
check("current_branch() returns same branch", branch == status.branch)
print(f"    current branch: {status.branch!r}")


print("\n[4] Working tree state")
check("clean is a bool", isinstance(status.clean, bool))
check("dirty property is inverse of clean", status.dirty == (not status.clean))
check("repository_clean() matches status.clean",
      reader.is_clean() == status.clean)
check("modified is a tuple", isinstance(status.modified, tuple))
check("untracked is a tuple", isinstance(status.untracked, tuple))
print(f"    clean={status.clean} "
      f"modified={len(status.modified)} "
      f"untracked={len(status.untracked)}")


print("\n[5] Last commit")
check("last_commit is a CommitInfo", isinstance(status.last_commit, CommitInfo))
check("short_hash is non-empty", bool(status.last_commit.short_hash))
check("short_hash is not 'unknown'", status.last_commit.short_hash != "unknown")
check("message is non-empty", bool(status.last_commit.message))
print(f"    {status.last_commit.short_hash} — {status.last_commit.message!r}")


print("\n[6] Summary")
summary = status.summary
check("summary is non-empty", len(summary) > 10)
check("summary contains branch", status.branch in summary)
check("summary contains commit hash",
      status.last_commit.short_hash in summary)
check("summary contains clean/dirty state",
      "clean" in summary or "dirty" in summary)
print(f"    {summary}")


print("\n[7] Modified files API")
modified = reader.modified_files()
check("modified_files() returns a list", isinstance(modified, list))
check("modified_files() consistent with status",
      set(modified) == set(status.modified))
untracked = reader.untracked_files()
check("untracked_files() returns a list", isinstance(untracked, list))
check("untracked_files() consistent with status",
      set(untracked) == set(status.untracked))


print("\n[8] Non-repository graceful fallback")
_tmp_dir = tempfile.mkdtemp()
reader_noRepo = GitReader(Path(_tmp_dir))
status_no = reader_noRepo.status()
check("non-repo returns GitStatus", isinstance(status_no, GitStatus))
check("non-repo available=False", not status_no.available)
check("non-repo has error message", bool(status_no.error))
check("non-repo summary is non-empty", bool(status_no.summary))
check("non-repo branch is 'unknown'", status_no.branch == "unknown")


print("\n[9] Read-only guarantee — behavioural")
# Verify GitReader exposes NO write methods by checking the public API.
# A method that modifies the repo would need to call git write commands —
# instead we confirm none of those names exist on the object at all.
write_method_names = [
    "add", "commit", "checkout", "merge",
    "push", "reset", "restore", "rm", "delete",
    "write", "create_branch", "switch_branch",
]
for method_name in write_method_names:
    check(f"GitReader has no .{method_name}() method",
          not hasattr(reader, method_name))
# Confirm the public API is strictly read-only by name
public_methods = [m for m in dir(reader) if not m.startswith("_")]
check("public API contains only read methods",
      all(m in ("status", "current_branch", "modified_files",
                "untracked_files", "is_clean", "last_commit",
                "repo_root")
          for m in public_methods))


print("\n[10] EngineeringCoordinator integration")
coord = EngineeringCoordinator(PROJECT_ROOT).initialise()

git_status = coord.git_status()
check("coord.git_status() returns GitStatus",
      isinstance(git_status, GitStatus))
check("coord.git_status() available", git_status.available)

branch = coord.current_branch()
check("coord.current_branch() returns string", isinstance(branch, str))
check("coord.current_branch() non-empty", bool(branch))

modified = coord.modified_files()
check("coord.modified_files() returns list", isinstance(modified, list))

clean = coord.repository_clean()
check("coord.repository_clean() returns bool", isinstance(clean, bool))

check("all coordinator methods consistent",
      git_status.branch == branch
      and set(git_status.modified) == set(modified)
      and git_status.clean == clean)

print(f"\n{'='*60}")
print(f"GENESIS-016 SPRINT 002: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now report:")
print(f"  current branch:    {branch!r}")
print(f"  repository clean:  {clean}")
print(f"  last commit:       {git_status.last_commit.short_hash}"
      f" — {git_status.last_commit.message!r}")
print(f"\nDeferred to later sprints:")
print(f"  git add, commit, branch creation, checkout, push, reset")