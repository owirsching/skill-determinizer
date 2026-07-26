# Pattern Library: Natural Language → Deterministic Code

Worked examples by category. Use these as models when classifying and
rewriting flagged phrases -- and as a reminder of vague phrasing the
regex scanner won't catch (it only matches literal phrase patterns; a lot
of vagueness is more contextual than that).

Each entry: vague original → deterministic replacement, with a note on
what to verify before writing it into a skill.

## Git / VCS

All of these are verified **in the actual repo the target SKILL.md lives
in**, on disposable branches/worktrees created just for the test and torn
down immediately after -- never on the user's current branch, never
pushed, never touching tracked files. See SKILL.md step 4 for the exact
safety sequence (check `git status` before and after, use obviously-
temporary names, clean up, and stop to ask the user if a test can't be
cleanly undone).

| Vague | Deterministic | Verify by |
|---|---|---|
| "checkout to a new branch" | `git checkout -b <name>` | creating a disposable branch in the real repo, confirming `git branch --show-current`, then switching back and deleting it |
| "checkout to a git worktree" | `git worktree add <path> -b <branch-name>` | adding a worktree at a temp path in the real repo, confirming path exists and branch checked out, then `git worktree remove --force` and deleting the branch |
| "commit with a good message" | exact template, e.g. `<type>(<scope>): <summary>` (conventional commits) | committing with the template on a disposable branch, checking `git log -1 --format=%s` matches pattern, then deleting that branch (never committing on the user's real branch) |
| "make sure the branch is up to date" | `git fetch origin && git rebase origin/main` (name rebase vs. merge explicitly) | running on a disposable branch cloned from the real repo's current state, never on the user's actual branch |
| "clean up the worktree after" | `git worktree remove <path> && git branch -d <name>` | confirming `git worktree list` no longer shows it and `git status` is back to the pre-test state |

## File / directory operations

| Vague | Deterministic | Verify by |
|---|---|---|
| "put it somewhere sensible" | exact path template, e.g. `./output/<date>-<slug>/` | running `mkdir -p` with a sample template, confirming path created |
| "set up a folder for this" | `mkdir -p <exact-path>` | as above |
| "clean up temp files" | `rm -rf ./tmp/<run-id>/` (scoped, never bare `rm -rf`) | creating dummy files, confirming only the scoped path is removed |
| "find the config file" | exact search order, e.g. `./config.yml` then `~/.config/tool/config.yml` | testing both paths exist/don't exist scenarios |

## Search / inspection

| Vague | Deterministic | Verify by |
|---|---|---|
| "look for X in the codebase" | `rg -n "pattern" --type ts` (exact flags/filetype) | running against a sample repo, confirming expected matches |
| "check if it's installed" | `command -v <tool> >/dev/null 2>&1 \|\| echo missing` | running with tool present and absent |

## Testing / linting / formatting / build / install

These are the phrases where guessing a generic default is the trap --
"run the tests" doesn't mean the same command in every repo. **Discover
the repo's real command first** with
`scripts/discover_environment_commands.py <repo-root>` (reads
package.json scripts, Makefile targets, pytest/ruff/black/mypy config in
pyproject.toml, lockfiles for npm/yarn/pnpm detection, and CI workflows as
low-confidence corroboration) rather than writing any of the table below
from memory. The table shows what the *discovered* replacement looks like
once you know the source, and what a generic (unverified) guess would have
looked like -- the point is to always land in the right-hand column via
discovery/verification, never by assumption.

| Vague | Generic guess (do NOT use without discovery) | Discovered + verified example | Verify by |
|---|---|---|---|
| "run the tests" / "run unit tests" | `pytest -x -q` or `npm test` | `make test` (because Makefile defines a `test` target) | running the discovered command in the real repo, confirming exit code 0 on the existing suite |
| "run the linter" | `eslint .` | `yarn lint` (because package.json's `scripts.lint` runs `eslint .` and yarn.lock is present) | running it, confirming it exits 0 on clean code and non-zero on a deliberately broken sample file |
| "format the code" | `prettier --write .` | `black .` (because pyproject.toml has `[tool.black]`) | running, diffing before/after on a sample file |
| "build the project" | `npm run build` | `make build` or `poetry build`, whichever the repo defines -- ask the user if both a Makefile and package.json define conflicting build steps | running the discovered command, confirming the expected build artifact appears |
| "install dependencies" | `pip install -r requirements.txt` | `poetry install` (because pyproject.toml is a poetry project) or `pnpm install` (because pnpm-lock.yaml is present) | running in a scratch clone/copy (installs can be slow/heavy -- don't run against the user's real environment repeatedly without asking) |
| "typecheck" | `mypy .` | `tsc --noEmit` (because it's a TypeScript project) or `mypy .` per discovered `[tool.mypy]` config | running, confirming it reports the expected errors on a sample file with a deliberate type error |

If discovery finds **no** source for a task, don't fall back to the
generic guess -- ask the user what command they actually run.

If discovery finds **conflicting** sources for the same task (e.g.
package.json's `test` script runs `jest` while the Makefile's `test`
target runs `pytest`), surface both to the user and ask which is
authoritative rather than picking one.

## Validation

| Vague | Deterministic | Verify by |
|---|---|---|
| "make sure it's valid JSON" | `jq . file.json > /dev/null \|\| echo invalid` | testing with valid and invalid JSON |
| "confirm the server is up" | explicit curl-retry loop with fixed interval/timeout, e.g. `for i in $(seq 1 10); do curl -sf http://localhost:PORT/health && break; sleep 2; done` | running against a server that starts slowly |
| "skip if already done" | `test -f .done-marker && exit 0` | running twice, confirming second run skips |

## Versioning

| Vague | Deterministic | Verify by |
|---|---|---|
| "bump the version" | `npm version patch` (or specify exact bump type -- patch/minor/major is a real ambiguity, ask the user) | running in scratch package, confirming version field changed |

## Environment / permissions

| Vague | Deterministic | Verify by |
|---|---|---|
| "activate the environment" | `source .venv/bin/activate` (literal path) | running, confirming `which python` points into venv |
| "make it executable" | `chmod +x script.sh` | confirming `ls -l` shows `x` bit |

## Templating / formatting output

| Vague | Deterministic | Verify by |
|---|---|---|
| "write a nice summary" | exact template with placeholders, not free text | filling the template with sample data, confirming output shape |
| "today's date" | `date +%Y-%m-%d` (pin the format -- locale-dependent formats are a real source of nondeterminism) | running and confirming format |

## Genuinely context-dependent (always ask, never default)

These look like they could be templated but actually require a real
decision from the user -- do not fill these in yourself:

- Naming conventions ("name it something descriptive") -- ask for the
  exact template (e.g. `<ticket-id>-<kebab-case-slug>`).
- Size/complexity thresholds ("if the file is large") -- ask for the exact
  cutoff (e.g. line count, byte size).
- Choice between multiple valid tools/approaches ("use the appropriate
  linter/formatter") -- ask for the exact per-language/per-context mapping.
- Style/tone preferences ("write it professionally") -- ask for concrete
  examples of the desired tone, or leave as prose if it's truly subjective.
