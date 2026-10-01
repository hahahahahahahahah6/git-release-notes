#!/usr/bin/env python3
"""
git-release-notes — release notes from `git log`, conventional-commit aware.

Zero dependencies, works fully offline. Run inside any git repo:

    git-release-notes [from] [to] [--verbose] [--json] [--title v1.2.0]

Defaults: `from` = most recent tag reachable from HEAD, `to` = HEAD.

Conventional-commit subjects (feat, fix, docs, chore, refactor, perf,
test, build, ci) are grouped into fixed sections; `!` markers and
BREAKING CHANGE footers get their own "Breaking Changes" section.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys

__version__ = "1.0.0"

KNOWN_TYPES = (
    "feat",
    "fix",
    "docs",
    "chore",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
)

# (key, heading, order) — fixed output order.
GROUP_ORDER = [
    ("breaking", "Breaking Changes"),
    ("feat", "Features"),
    ("fix", "Fixes"),
    ("docs", "Documentation"),
    ("chore", "Chores"),
    ("refactor", "Refactors"),
    ("perf", "Performance"),
    ("test", "Tests"),
    ("build", "Build"),
    ("ci", "CI"),
    ("other", "Other changes"),
]

_TYPE_TO_GROUP = {key: key for key, _ in GROUP_ORDER if key != "breaking"}
_COLLAPSED_GROUP = "other"

_SUBJECT_RE = re.compile(
    r"^(?P<type>[A-Za-z]+)(?P<scope>\([^()\r\n]*\))?(?P<bang>!)?\s*:\s*(?P<subject>.*)$"
)
# Only a footer line counts: "BREAKING CHANGE:" / "BREAKING-CHANGE:" at the
# start of a line. A mere mention ("this is not a breaking change") does not.
_BREAKING_RE = re.compile(r"(?m)^BREAKING[- ]CHANGE:", re.IGNORECASE)


class GitError(RuntimeError):
    """A git command failed; carry the message to show the user."""


def _run_git(*args):
    try:
        proc = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        raise GitError("git is not installed or not on PATH")
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def ensure_git_repo():
    try:
        _run_git("rev-parse", "--git-dir")
    except GitError:
        print(
            "error: not inside a git repository "
            "(git-release-notes must run in a git repo)",
            file=sys.stderr,
        )
        sys.exit(2)


def most_recent_tag():
    """Most recent tag reachable from HEAD, or None if there are no tags."""
    try:
        return _run_git("describe", "--tags", "--abbrev=0", "HEAD").strip()
    except GitError:
        return None


def previous_tag(tag):
    """The nearest tag reachable before `tag`'s commit, or None.

    Used when the range is empty because the tag sits on HEAD: fall back
    to the previous release instead of printing a bare "No changes."
    """
    try:
        return _run_git("describe", "--tags", "--abbrev=0", tag + "^").strip()
    except GitError:
        return None


def _same_commit(a, b):
    """True if two refs resolve to the same commit (fail-open: False)."""
    try:
        ra = _run_git("rev-parse", a + "^{commit}").strip()
        rb = _run_git("rev-parse", b + "^{commit}").strip()
        return bool(ra) and ra == rb
    except GitError:
        return False


def parse_subject(subject):
    """Split a conventional-commit subject into (type, bang, clean_text)."""
    m = _SUBJECT_RE.match(subject)
    if not m:
        return None, False, subject
    ctype = m.group("type").lower()
    if ctype not in KNOWN_TYPES:
        # Not a type we group on: keep the whole subject, treat as "other".
        return None, False, subject
    text = m.group("subject").strip() or subject
    return ctype, bool(m.group("bang")), text


def collect_commits(from_ref, to_ref):
    """Return a list of dicts: {sha, short, type, breaking, text}."""
    spec = f"{from_ref}..{to_ref}" if from_ref else to_ref
    raw = _run_git(
        "log",
        "--no-decorate",
        "--no-merges",
        "--format=%H%x1f%h%x1f%s%x1f%b%x1e",
        spec,
    )
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) < 4:
            continue
        full, short, subject, body = parts[0], parts[1], parts[2], parts[3]
        ctype, bang, text = parse_subject(subject)
        breaking = bang or bool(_BREAKING_RE.search(body))
        commits.append(
            {
                "sha": full,
                "short": short,
                "type": ctype,
                "breaking": breaking,
                "text": text,
            }
        )
    return commits


def group_commits(commits, verbose=False):
    """Bucket commits into (heading, entries) in fixed order. Skips empties."""
    buckets = {key: [] for key, _ in GROUP_ORDER}
    for c in commits:
        if c["breaking"]:
            buckets["breaking"].append(c)
        elif c["type"] is None:
            buckets["other"].append(c)
        elif verbose or c["type"] in ("feat", "fix"):
            buckets[c["type"]].append(c)
        else:
            # docs/chore/etc collapse into "Other changes" by default
            buckets[_COLLAPSED_GROUP].append(c)
    return [
        (heading, buckets[key])
        for key, heading in GROUP_ORDER
        if buckets[key]
    ]


def render_markdown(groups, title=None, date=None):
    lines = []
    if title:
        head = f"# {title}"
        if date:
            head += f" — {date}"
        lines.append(head)
        lines.append("")
    for heading, entries in groups:
        lines.append(f"## {heading}")
        lines.append("")
        for e in entries:
            lines.append(f"- {e['text']} ({e['short']})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(groups, from_ref, to_ref, title=None, date=None):
    return json.dumps(
        {
            "version": title,
            "date": date,
            "from": from_ref,
            "to": to_ref,
            "groups": [
                {
                    "name": heading,
                    "entries": [
                        {"subject": e["text"], "sha": e["short"]}
                        for e in entries
                    ],
                }
                for heading, entries in groups
            ],
        },
        indent=2,
    ) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="git-release-notes",
        description="Grouped markdown release notes from git log, "
        "conventional-commit aware. Offline, zero dependencies.",
    )
    ap.add_argument(
        "from_ref",
        nargs="?",
        default=None,
        help="start of range (default: most recent tag reachable from HEAD)",
    )
    ap.add_argument(
        "to_ref", nargs="?", default="HEAD", help="end of range (default: HEAD)"
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help='split "Other changes" into per-type groups '
        "(docs, chore, refactor, ...)",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--title",
        dest="title",
        default=None,
        help='prepend a "# <title>" heading with today\'s date',
    )
    ap.add_argument(
        "--version",
        action="store_true",
        help="print the tool version and exit",
    )
    args = ap.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    ensure_git_repo()

    from_ref = args.from_ref or most_recent_tag()
    try:
        commits = collect_commits(from_ref, args.to_ref)
    except GitError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if not commits and from_ref and _same_commit(from_ref, args.to_ref):
        # Most common trigger: you just tagged the release and ran with no
        # args, so the default range is empty. Fall back to the previous tag
        # instead of printing a bare "No changes."
        prev = previous_tag(from_ref)
        if prev:
            print(
                f"note: no commits since {from_ref}; "
                f"showing changes since {prev}.",
                file=sys.stderr,
            )
            from_ref = prev
            try:
                commits = collect_commits(from_ref, args.to_ref)
            except GitError as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(2)
        else:
            # Only one tag and it sits on HEAD: nothing older to fall back
            # to, so show the full history instead of "No changes."
            print(
                f"note: no commits since {from_ref}; "
                f"showing full history.",
                file=sys.stderr,
            )
            from_ref = None
            try:
                commits = collect_commits(from_ref, args.to_ref)
            except GitError as exc:
                print(f"error: {exc}", file=sys.stderr)
                sys.exit(2)

    if not commits:
        print("No changes.")
        return 0

    groups = group_commits(commits, verbose=args.verbose)
    date = _dt.date.today().isoformat() if args.title else None

    if args.json:
        sys.stdout.write(
            render_json(groups, from_ref, args.to_ref, args.title, date)
        )
    else:
        sys.stdout.write(render_markdown(groups, args.title, date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
