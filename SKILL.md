---
name: skill-determinizer
description: Converts a SKILL.md's natural-language instructions into deterministic, verified code and commands wherever possible -- e.g. turning "checkout to a git worktree" into an exact "git worktree add" invocation, or "run the unit tests" into whatever command this repo's own package.json/Makefile/pytest config actually defines. Use whenever the user wants to make an existing skill more precise, reliable, or reproducible; wants to "remove ambiguity," "harden," "de-fuzz," or "convert to exact commands"; wants Claude to learn how their environment/repo actually runs tasks like tests, builds, linting, or installs; or asks you to review a SKILL.md for vague language, hedge words, or judgment calls that should instead be pinned to an exact command, path, value, or decision table.
---

# Skill Determinizer

A skill for auditing an existing SKILL.md and replacing every place where it
currently relies on a model's judgment call -- naming something "sensible,"
"cleaning up appropriately," "checking that it works" -- with something a
computer can execute the same way every single time: an exact shell command,
an exact path/template, an exact numeric threshold, or an explicit
if/then decision table.

The core principle: **if a step could be a deterministic command, it should
be one.** Natural language is for judgment calls that genuinely can't be
pinned down in advance. Everything else is a bug waiting to happen -- two
different runs of the same skill producing two different outputs because
the instruction said "format it nicely" instead of `prettier --write .`.

## Non-negotiable rules

1. **Never write an unverified command into the target skill.** Every
   proposed command must actually be run and confirmed to work before it
   goes into the rewritten SKILL.md. A "deterministic" instruction that's
   actually broken is worse than the vague prose it replaced. For
   git/repo-related commands specifically, verify **in the actual git repo
   that the target SKILL.md lives in** (not a synthetic scratch repo
   elsewhere) -- real remotes, hooks, config, and repo state are what the
   skill will actually run against, and a command that works in a fresh
   throwaway repo can behave differently in the real one. Verifying in the
   real repo means taking real precautions (see step 6) so verification
   never leaves behind branches, worktrees, commits, or file changes the
   user didn't ask for.
2. **Never invent a naming convention, threshold, or style choice on the
   user's behalf.** If a phrase is ambiguous because it's genuinely
   context-dependent (e.g. "name it something descriptive", "if the file is
   large", "use the appropriate linter"), ask the user for the exact rule.
   Do not default to a plausible-sounding template and move on -- the whole
   point of this skill is to stop guessing.
3. **Don't over-rewrite.** Some natural language is there on purpose (e.g.
   "explain the tradeoffs to the user in plain language," "use your
   judgment about tone"). Leave genuinely judgment-requiring instructions
   alone. The goal is removing accidental ambiguity, not eliminating all
   prose.

## Process

### 1. Read the target SKILL.md

Read the whole file (and any bundled `references/`, `scripts/` it points
to) before touching anything, so you understand what the skill is actually
trying to accomplish.

### 2. Scan for candidate phrases

Run the bundled scanner:

```bash
python3 scripts/scan_vague_language.py <path-to-target-SKILL.md>
```

This returns a JSON list of `{line_number, line_text, category,
matched_phrase, reason}`. Treat this as a starting list of *candidates*,
not a checklist to blindly action -- it will over-flag (e.g. "Good luck!"
at the end of a skill, or "figure out what the skill is about" in a
meta-sentence about skill-building itself, not about a task step). Read
each flagged line in context before deciding what to do with it.

See `references/pattern_library.md` for the categories the scanner looks
for and a larger set of worked examples (git, file ops, testing, linting,
validation, versioning, etc.) to help you recognize additional vague
phrasing the regex-based scanner will miss -- the scanner is a net, not a
replacement for reading.

### 3. Classify every candidate into one of three buckets

For each flagged (or manually spotted) phrase:

- **(a) Deterministic candidate** -- the underlying action has one exact,
  checkable implementation (a shell command, an exact path, an exact
  file/API call). Draft the replacement command.
- **(b) Context-dependent convention** -- the ambiguity is real (a naming
  scheme, a size/complexity threshold, which of several valid tools to use,
  a style preference) and there's no single objectively-correct answer.
  **Ask the user** what the exact rule should be -- do not guess a default.
  Batch these questions together rather than asking one at a time.
- **(c) Intentional judgment call** -- leave it alone. Note briefly why (so
  the user can see your reasoning if they review the diff).
- **(d) Hardcoded but wrong for this repo** -- not caught by the scanner
  above at all, since nothing about it reads as vague. A command like
  `npm test` embedded as a worked example is fully specified -- it's just
  specified for the wrong ecosystem if the target repo is actually
  Gradle/Maven/Go/Rust/etc. This is worse than vague language in one
  respect: vague language at least signals "there's a blank to fill in,"
  while a wrong-but-confident command looks authoritative and won't get
  questioned. See step 5 for how this gets detected -- it requires the
  target repo, not just the SKILL.md text, so it can't be caught by
  `scan_vague_language.py` alone.

### 4. For task-oriented phrases, discover the repo's real command instead of guessing one

Phrases like "run the unit tests," "run the linter," "build the project,"
"install dependencies," or "start the dev server" are bucket-(a)
deterministic candidates, but the exact command is project-specific --
guessing a plausible default (`pytest`, `npm test`, `make build`) is
exactly the kind of unverified assumption this skill exists to eliminate.
Instead, discover what *this* repo actually uses:

```bash
python3 scripts/discover_environment_commands.py <path-to-repo-root>
```

This reads the repo's own package.json scripts, Makefile targets, Python
tooling config (pytest.ini/tox.ini/pyproject.toml `[tool.pytest]`,
`[tool.ruff]`, `[tool.black]`, `[tool.mypy]`), lockfiles (to pick
npm/yarn/pnpm correctly), and CI workflow files (`.github/workflows/*.yml`,
treated as low-confidence corroborating evidence only, since CI commands
often carry extra flags irrelevant to local runs), and reports the
discovered command per task with its source.

- **Single source found** -- use the discovered command as the
  replacement (e.g. "run unit tests" -> `make test`, because the repo's
  own Makefile defines that target). This is still a bucket-(a) command
  and still needs to be verified per step 6 before it goes in the skill.
- **No source found** -- don't fall back to a generic guess. Treat it like
  a bucket-(b) item and ask the user what command they actually use.
- **Conflicting sources found** (e.g. package.json's `test` script runs
  `jest` but the Makefile's `test` target runs `pytest`) -- do not pick one
  yourself. Tell the user what each source says and ask which is
  authoritative for this skill's purposes.

### 5. Check for hardcoded commands that don't match this repo's ecosystem

This catches bucket-(d) issues -- commands the skill already states with
full confidence, but for the wrong tooling. The whole point of
determinizing a skill is tailoring it to the repo/workflow it's actually
going to run against, so no tokens get spent guessing -- a hardcoded
command from the wrong ecosystem defeats that just as badly as a vague
one does, and reads as more trustworthy while doing it.

```bash
python3 scripts/detect_ecosystem_mismatch.py <path-to-target-SKILL.md> <path-to-repo-root>
```

This extracts every inline-code and fenced-code-block command in the
SKILL.md, classifies each by ecosystem (node/python/gradle/maven/go/
rust/ruby, by tool prefix), compares against the repo's actual detected
ecosystem(s) (by marker files: `package.json`, `pyproject.toml`,
`build.gradle(.kts)`, `pom.xml`, `go.mod`, `Cargo.toml`, `Gemfile`), and
flags any command whose ecosystem isn't among the repo's.

- **Mismatch found** -- replace the hardcoded command with the correct
  one for this repo, using `discover_environment_commands.py` (step 4) to
  find the actual replacement. Verify it per step 6 before writing it in.
- **No repo ecosystem detected at all** -- the script stays silent rather
  than guessing; don't manually flag anything either in that case.
- Remember this is about the *target* repo specifically (see the
  non-negotiable rules on treating a skill as scoped to one repo vs.
  portable across many) -- a skill meant to be portable across ecosystems
  legitimately needs conditional logic here, not a single hardcoded
  replacement; only collapse to one command if the skill is meant to be
  repo-specific.

### 6. Verify every (a)-bucket command before writing it down

**Git/repo commands are verified inside the actual repo the target
SKILL.md lives in.** Non-repo commands (file ops on scratch files, jq/curl
checks, formatters, etc.) can still use a throwaway temp directory since
there's no "real repo state" for those to diverge from.

Before running anything against the real repo:

- `cd` into the repo and run `git status --porcelain` and
  `git branch --show-current` first. If the working tree is dirty or
  you're not sure the state is safe to test against, stop and tell the
  user rather than guessing.
- Never run a verification command that mutates `main`/`master`, the
  currently checked-out branch, tracked files, or anything not created by
  this verification step. Every test happens on disposable state you
  create and then remove:
  - Branch-creating commands (`git checkout -b`, `git branch`) -> create
    with an obviously-temporary name (e.g. `determinizer-verify-<n>`),
    verify, then `git checkout -` back to the original branch and
    `git branch -D determinizer-verify-<n>`.
  - Worktree commands (`git worktree add`) -> add under a temp path (e.g.
    `../determinizer-verify-wt`), verify, then
    `git worktree remove --force <path>` and delete the branch it created.
  - Commit-creating commands -> commit only on a disposable branch (never
    the branch the user was on), and delete that branch afterward. Never
    run anything that pushes to a remote.
  - Rebase/merge commands -> run only on a disposable branch cloned from
    current state, never on the user's actual branch, so a bad rebase
    can't corrupt their history.
- Never run destructive commands (force-push, `reset --hard` on a real
  branch, history rewrites) against the real repo even on a disposable
  branch, unless the user explicitly confirms first.
- After verifying, run `git status --porcelain` and
  `git branch --show-current` again to confirm the repo is back to exactly
  the state it was in before -- no stray branches, worktrees, or file
  changes left behind.

For every command tested:
- Actually execute it via the bash tool -- never mark something verified
  based on reasoning alone.
- Confirm it does what the prose said it should (right exit code, right
  branch/file produced, right output shape) -- don't just check that it
  didn't error.
- If it fails or behaves subtly differently than the prose implied, fix
  the command and re-test. Iterate until it's confirmed, not just
  plausible.
- Note what you verified (command + one-line result, and confirmation
  that cleanup restored the original repo state) so you can show your work
  to the user.

If at any point you're not confident a test can be cleanly undone, stop
and ask the user before proceeding rather than risking their repo.

### 7. Fold in the user's answers from bucket (b)

Once the user has supplied the exact conventions for any context-dependent
items, turn those into deterministic rules too (a template string, a
decision table, an exact numeric cutoff) and verify them the same way as
step 6 where they're executable (e.g. test the naming template actually
produces a valid branch/file name; a pure style preference like "always
use present tense" doesn't need execution, just needs to be written down
precisely). This also covers task commands that step 4 couldn't discover
or that had conflicting sources, and ecosystem replacements from step 5 --
once the user tells you which command is authoritative, verify it the
same way as any other bucket-(a) command.

### 8. Present a before/after diff

For every changed line or block, show:
- The original prose
- The replacement (exact command / template / decision table)
- What was verified, briefly (e.g. "ran `git worktree add
  ../determinizer-verify-wt -b determinizer-verify-1` in this repo --
  confirmed worktree created and branch checked out, then removed the
  worktree and deleted the branch, confirmed `git status` clean and back
  on original branch")

Get the user's confirmation before finalizing, since some rewrites may be
more verbose than the original prose and the user should sign off on the
tradeoff.

### 9. Write the final SKILL.md

Apply the confirmed changes. If a bucket-(a) rewrite is more than a couple
of lines (e.g. a multi-step validation loop), consider moving it into a
bundled `scripts/` file instead of inlining it in the markdown, and have
the SKILL.md body just call the script -- this is itself a determinism win,
since a script can't be paraphrased differently on different runs the way
inline prose instructions describing a multi-step process might be
interpreted differently.

## Reference

`references/pattern_library.md` has a larger catalogue of natural-language
→ deterministic-code conversions across git/VCS, file operations, search,
testing/linting/formatting, validation, versioning, environment/permissions,
and templating -- useful both as scanner categories and as prompts for
things a regex won't catch.

`scripts/discover_environment_commands.py` inspects a repo's own
package.json/Makefile/Python tooling config/Gradle/Maven/CI files to find
the commands it actually uses for test/build/lint/format/typecheck/
install/dev tasks, so "run the unit tests" gets converted into this
project's real command rather than a generic guess.

`scripts/detect_ecosystem_mismatch.py` catches the opposite failure mode
-- a hardcoded command in the SKILL.md that's fully specified but for the
wrong ecosystem (e.g. `npm test` baked into a skill that's now being
pointed at a Kotlin/Gradle repo). Not detectable by the vague-language
scanner, since nothing about a hardcoded command reads as vague.
