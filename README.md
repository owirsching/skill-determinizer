# skill-determinizer

Claude Code skill that rewrites vague `SKILL.md` instructions ("run the
tests," "clean up appropriately") into exact, verified commands, paths, and
decision tables. Ambiguous conventions (naming, thresholds, tool choice) are
asked about, not guessed. Every proposed command is actually run and
verified before it's written into the skill.

## Install

**Plugin marketplace:**
```
/plugin marketplace add owirsching/skill-determinizer
/plugin install skill-determinizer@skill-determinizer
```

**git clone:**
```bash
git clone https://github.com/owirsching/skill-determinizer.git ~/.claude/skills/skill-determinizer
```

**curl:**
```bash
mkdir -p ~/.claude/skills/skill-determinizer
curl -L https://github.com/owirsching/skill-determinizer/archive/refs/heads/main.tar.gz \
  | tar -xz -C ~/.claude/skills/skill-determinizer --strip-components=1
```

Use `.claude/skills/` instead of `~/.claude/skills/` for a project-local
install. Restart Claude Code if the skills directory is new.

## Usage

> Determinize the SKILL.md at `./skills/my-skill/SKILL.md` — this repo uses
> pytest and a Makefile.

Claude scans for vague phrasing, classifies each instance, discovers this
repo's real test/build/lint commands, verifies replacements by running
them, and shows a before/after diff for approval.

## Contents

- `SKILL.md` — skill definition
- `scripts/scan_vague_language.py` — flags vague phrasing
- `scripts/discover_environment_commands.py` — finds a repo's real
  test/build/lint/install commands
- `scripts/detect_ecosystem_mismatch.py` — flags hardcoded commands for the
  wrong ecosystem
- `references/pattern_library.md` — catalogue of natural-language →
  deterministic-command conversions
