"""Smoke tests for git-release-notes.

Builds throwaway git repos in tmp dirs (git init / commits / tags via
subprocess) and runs the CLI against them. Skips everything if the git
binary is missing.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

CLI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "git_release_notes.py")

GIT = shutil.which("git")
needs_git = unittest.skipIf(GIT is None, "git binary not available")


def sh(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


@needs_git
class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="grn-")
        sh("git", "init", cwd=self.repo)
        sh("git", "config", "user.email", "test@example.com", cwd=self.repo)
        sh("git", "config", "user.name", "Test", cwd=self.repo)
        out = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=self.repo, capture_output=True, text=True)
        self.branch = out.stdout.strip() or "master"

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    # helpers -------------------------------------------------------------
    def commit(self, msg, body=""):
        fname = f"f{len(os.listdir(self.repo))}.txt"
        with open(os.path.join(self.repo, fname), "w") as f:
            f.write(msg)
        sh("git", "add", ".", cwd=self.repo)
        args = ["git", "commit", "-m", msg]
        if body:
            args += ["-m", body]
        sh(*args, cwd=self.repo)

    def tag(self, name):
        sh("git", "tag", name, cwd=self.repo)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, CLI, *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )

    # tests ---------------------------------------------------------------
    def test_grouping_correct(self):
        self.commit("chore: initial scaffolding")
        self.tag("v0.1.0")
        self.commit("feat(auth): add login form")
        self.commit("fix: crash on empty input")
        self.commit("docs: update readme")
        out = self.run_cli("v0.1.0", "HEAD")
        self.assertEqual(out.returncode, 0)
        text = out.stdout
        self.assertIn("## Features", text)
        self.assertIn("- add login form (", text)
        self.assertIn("## Fixes", text)
        self.assertIn("- crash on empty input (", text)
        # docs collapsed into "Other changes" by default
        self.assertNotIn("## Documentation", text)
        self.assertIn("## Other changes", text)
        self.assertIn("- update readme (", text)
        # fixed group order: Features before Fixes before Other
        self.assertLess(text.index("## Features"), text.index("## Fixes"))
        self.assertLess(text.index("## Fixes"), text.index("## Other changes"))

    def test_breaking_change_detected(self):
        self.commit("feat: first")
        self.tag("v0.1.0")
        self.commit("feat!: drop legacy auth API")
        self.commit("refactor: rework config", body="BREAKING CHANGE: env var renamed")
        self.commit("feat: add new widget")
        out = self.run_cli("v0.1.0", "HEAD")
        text = out.stdout
        self.assertIn("## Breaking Changes", text)
        self.assertIn("- drop legacy auth API (", text)
        self.assertIn("- rework config (", text)
        # breaking section comes first
        self.assertLess(text.index("## Breaking Changes"), text.index("## Features"))

    def test_empty_range_no_changes(self):
        self.commit("feat: something")
        self.tag("v1.0.0")
        out = self.run_cli("v1.0.0", "HEAD")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "No changes.")

    def test_json_valid(self):
        self.commit("chore: baseline")
        self.tag("v0.1.0")
        self.commit("feat: one")
        self.commit("fix: two")
        out = self.run_cli("v0.1.0", "HEAD", "--json")
        self.assertEqual(out.returncode, 0)
        data = json.loads(out.stdout)
        self.assertEqual(data["from"], "v0.1.0")
        self.assertEqual(data["to"], "HEAD")
        names = [g["name"] for g in data["groups"]]
        self.assertEqual(names, ["Features", "Fixes"])
        self.assertEqual(data["groups"][0]["entries"][0]["subject"], "one")
        self.assertRegex(data["groups"][0]["entries"][0]["sha"], r"^[0-9a-f]{7}$")

    def test_title_heading(self):
        self.commit("feat: one")
        self.tag("v0.1.0")
        self.commit("feat: two")
        out = self.run_cli("v0.1.0", "HEAD", "--title", "v1.2.0")
        self.assertEqual(out.returncode, 0)
        self.assertRegex(out.stdout, r"^# v1\.2\.0 — \d{4}-\d{2}-\d{2}\n")

    def test_version_flag_prints_tool_version(self):
        out = self.run_cli("--version")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), "1.0.0")

    def test_breaking_needs_footer_line(self):
        # "breaking change" mentioned in prose is NOT a breaking change.
        self.commit("feat: first")
        self.tag("v0.1.0")
        self.commit("fix: tweak", body="This is not a breaking change.")
        self.commit("fix: other", body="note: BREAKING CHANGE mentioned mid-line")
        self.commit("refactor: dash form", body="BREAKING-CHANGE: api removed")
        out = self.run_cli("v0.1.0", "HEAD")
        text = out.stdout
        self.assertIn("## Breaking Changes", text)
        self.assertIn("- dash form (", text)
        self.assertNotIn("tweak", text.split("## Breaking Changes")[1].split("##")[0])
        self.assertNotIn("other", text.split("## Breaking Changes")[1].split("##")[0])

    def test_merge_commits_excluded(self):
        self.commit("feat: base")
        self.tag("v0.1.0")
        sh("git", "checkout", "-qb", "side", cwd=self.repo)
        self.commit("feat: side work")
        sh("git", "checkout", "-q", self.branch, cwd=self.repo)
        sh("git", "merge", "--no-ff", "-qm", "Merge branch 'side'", "side",
           cwd=self.repo)
        out = self.run_cli("v0.1.0", "HEAD")
        text = out.stdout
        self.assertIn("side work", text)
        self.assertNotIn("Merge branch", text)

    def test_empty_range_falls_back_to_previous_tag(self):
        self.commit("feat: old")
        self.tag("v0.1.0")
        self.commit("feat: between")
        self.tag("v0.2.0")  # tag sits on HEAD: default range is empty
        out = self.run_cli()
        self.assertEqual(out.returncode, 0)
        self.assertIn("- between (", out.stdout)
        self.assertIn("no commits since v0.2.0", out.stderr)

    def test_verbose_splits_other(self):
        self.commit("chore: scaffolding")
        self.tag("v0.1.0")
        self.commit("docs: write guide")
        self.commit("chore: bump deps")
        out = self.run_cli("v0.1.0", "HEAD", "--verbose")
        text = out.stdout
        self.assertIn("## Documentation", text)
        self.assertIn("## Chores", text)
        self.assertNotIn("## Other changes", text)

    def test_default_from_is_latest_tag(self):
        self.commit("feat: old")
        self.tag("v0.1.0")
        self.commit("feat: between tags")
        self.tag("v0.2.0")
        self.commit("fix: only this one")
        out = self.run_cli()
        self.assertEqual(out.returncode, 0)
        self.assertIn("- only this one (", out.stdout)
        self.assertNotIn("between tags", out.stdout)

    def test_subject_prefix_stripped(self):
        self.commit("chore: baseline")
        self.tag("v0.1.0")
        self.commit("feat(api): add endpoint")
        self.commit("feat: plain one")
        out = self.run_cli("v0.1.0", "HEAD")
        self.assertIn("- add endpoint (", out.stdout)
        self.assertIn("- plain one (", out.stdout)


@needs_git
class RepoCheckTest(unittest.TestCase):
    def test_not_a_git_repo_exits_2(self):
        tmp = tempfile.mkdtemp(prefix="grn-norepo-")
        self.addCleanup(shutil.rmtree, tmp, True)
        out = subprocess.run(
            [sys.executable, CLI], cwd=tmp, capture_output=True, text=True
        )
        self.assertEqual(out.returncode, 2)
        self.assertIn("not inside a git repository", out.stderr)


if __name__ == "__main__":
    unittest.main()
