# git-release-notes

Release notes from `git log`, conventional-commit aware. Zero dependencies, works fully offline.

## The pain

It's release day. You tag the release, then stare at 40 commits trying to remember what actually shipped. So you scroll through a raw log, copy-paste subject lines into a text file, squint at which ones are features and which are just chores, and miss the one breaking change buried at commit #27.

`git-release-notes` does that archaeology for you — in one command, offline.

## Install

It's a single file, stdlib only (Python 3.9+). Pick one:

```bash
# download and run anywhere
curl -O https://raw.githubusercontent.com/hahahahahahahahah6/git-release-notes/main/git_release_notes.py
chmod +x git_release_notes.py

# or clone and alias
git clone https://github.com/hahahahahahahahah6/git-release-notes
alias git-release-notes="$PWD/git-release-notes/git_release_notes.py"
```

No pip, no virtualenv, no network. `git` itself is the only other thing you need (it's already there if you're releasing).

## Usage

```bash
git-release-notes [from] [to] [--verbose] [--json] [--version v1.2.0]
```

- `from` defaults to the most recent tag reachable from HEAD, `to` defaults to HEAD.
- Must run inside a git repo (friendly error, exit 2, otherwise).
- No commits in range → prints `No changes.`, exit 0.

Realistic example — you just merged a sprint's worth of work after `v1.3.0`:

```bash
$ git-release-notes
## Breaking Changes

- drop legacy auth endpoints (9f2c41a)

## Features

- add login form (e4b7d21)
- dark mode toggle (7c0a55f)

## Fixes

- crash on empty input (a91be30)

## Other changes

- update readme (3d55f12)
- bump deps (6f0e8a4)
```

Options:

```bash
git-release-notes v1.2.0 v1.3.0          # explicit range
git-release-notes --verbose              # docs/chore/etc get their own sections
git-release-notes --json                 # machine-readable
git-release-notes --version v1.4.0       # prepend "# v1.4.0 — 2026-10-01"
git-release-notes | pbcopy               # pipe it into your release page
```

Conventional-commit parsing:

- Grouped types: `feat`, `fix`, `docs`, `chore`, `refactor`, `perf`, `test`, `build`, `ci`
- `feat(scope): subject` → subject with the prefix stripped
- `!` marker or `BREAKING CHANGE:` footer → goes in **Breaking Changes** (first section)
- Everything else collapses into **Other changes** unless `--verbose` splits it out

## Differentiation

This is **not** a GitHub-Action release drafter.

- **Offline** — no GitHub API, no tokens, no CI workflow to wire up. Works on a plane, in a monorepo, on a bare server.
- **Zero dependencies** — one file, stdlib only. Download it and run it; nothing to install.
- **Conventional-commit aware** — types and breaking-change markers are parsed and grouped, not dumped raw.
- **Pipeable** — markdown to stdout means `| pbcopy`, `| tee`, or straight into your release tooling. `--json` for scripts.

## License

MIT — see [LICENSE](LICENSE).
