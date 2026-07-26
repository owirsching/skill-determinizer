#!/usr/bin/env python3
"""
Detect hardcoded commands in a SKILL.md that belong to a different
ecosystem than the actual target repo uses -- e.g. a skill that hardcodes
`npm test` as a worked example, pointed at a Kotlin/Gradle repo.

This is a DIFFERENT failure mode than what scan_vague_language.py looks
for. A vague phrase ("run the appropriate tests") is honest about not
knowing the answer -- a reader has to fill in the blank, but at least
knows there's a blank. A hardcoded-but-wrong command is worse: it reads as
authoritative and precise, so nothing about it looks like a problem, but
following it literally runs the wrong tool for this repo. The vague-
language scanner can't catch this because nothing here is vague -- the
scanner only flags underspecified phrasing, and `npm test` is about as
specified as a command gets. This script exists to catch that other case.

Usage:
    python3 detect_ecosystem_mismatch.py <path-to-SKILL.md> <path-to-target-repo>

Output: JSON list of {line_number, line_text, command, command_ecosystem,
repo_ecosystems, reason}
"""
import sys
import os
import re
import json

# Marker files that identify a repo's ecosystem(s). A repo can legitimately
# match more than one (e.g. a Python repo with a small Node-based docs
# site) -- that's fine, a hardcoded command only gets flagged if its
# ecosystem ISN'T among any of the ones actually detected.
ECOSYSTEM_MARKERS = {
    "node": ["package.json"],
    "python": ["pyproject.toml", "requirements.txt", "setup.py", "Pipfile"],
    "gradle": ["build.gradle", "build.gradle.kts"],
    "maven": ["pom.xml"],
    "go": ["go.mod"],
    "rust": ["Cargo.toml"],
    "ruby": ["Gemfile"],
}

# Command prefixes that identify which ecosystem a hardcoded command
# belongs to. Ordered longest-prefix-first within lookup so e.g.
# "npm run test" doesn't get missed by a shorter unrelated match.
COMMAND_ECOSYSTEM_PATTERNS = [
    (re.compile(r"^\s*(npm|npx|yarn|pnpm)\b"), "node"),
    (re.compile(r"^\s*(pytest|pip|pip3|python|python3|poetry|uv|pipenv)\b"), "python"),
    (re.compile(r"^\s*(\./gradlew|gradle)\b"), "gradle"),
    (re.compile(r"^\s*mvn\b"), "maven"),
    (re.compile(r"^\s*go\s+(test|build|run|mod)\b"), "go"),
    (re.compile(r"^\s*cargo\b"), "rust"),
    (re.compile(r"^\s*bundle\b|^\s*rspec\b"), "ruby"),
]

# Inline code spans (`...`) and fenced code block lines are where hardcoded
# commands actually live in a SKILL.md -- prose sentences describing a
# command in words aren't what this script is for (that's the vague-
# language scanner's job when the wording is vague, and just correct prose
# otherwise).
INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def detect_repo_ecosystems(repo_path):
    ecosystems = set()
    for ecosystem, markers in ECOSYSTEM_MARKERS.items():
        for marker in markers:
            if os.path.exists(os.path.join(repo_path, marker)):
                ecosystems.add(ecosystem)
                break
    return ecosystems


def classify_command_ecosystem(command_text):
    for pattern, ecosystem in COMMAND_ECOSYSTEM_PATTERNS:
        if pattern.search(command_text):
            return ecosystem
    return None


def extract_candidate_commands(skill_md_path):
    """Return [(line_number, line_text, command_text)] for every inline-code
    span or fenced-code-block line that looks like a command (i.e. we can
    classify it into a known ecosystem). Prose that merely mentions a tool
    by name without it being in code formatting is intentionally not
    picked up -- this script only checks things presented as literal
    commands to run, not narrative discussion of them."""
    with open(skill_md_path) as f:
        lines = f.readlines()

    candidates = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            if stripped:
                # Strip a leading shell-prompt marker ("$ npm test" is a
                # very common convention for "here's what you'd type") so
                # the command classifier can match the actual tool name
                # instead of failing to match "$" as a prefix.
                command_text = re.sub(r"^\$\s*", "", stripped)
                candidates.append((i, line.rstrip("\n"), command_text))
            continue
        for m in INLINE_CODE_RE.finditer(line):
            candidates.append((i, line.rstrip("\n"), m.group(1)))
    return candidates


def find_mismatches(skill_md_path, repo_path):
    repo_ecosystems = detect_repo_ecosystems(repo_path)
    candidates = extract_candidate_commands(skill_md_path)

    mismatches = []
    for line_number, line_text, command_text in candidates:
        cmd_ecosystem = classify_command_ecosystem(command_text)
        if cmd_ecosystem is None:
            continue  # not a recognizable command, nothing to check
        if not repo_ecosystems:
            continue  # unknown repo type -- nothing to compare against, don't guess
        if cmd_ecosystem not in repo_ecosystems:
            mismatches.append({
                "line_number": line_number,
                "line_text": line_text,
                "command": command_text,
                "command_ecosystem": cmd_ecosystem,
                "repo_ecosystems": sorted(repo_ecosystems),
                "reason": (
                    f"This command belongs to the {cmd_ecosystem} ecosystem, "
                    f"but the target repo's detected ecosystem(s) are "
                    f"{sorted(repo_ecosystems)} -- following this command "
                    f"literally would run the wrong tool for this repo."
                ),
            })
    return mismatches


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 detect_ecosystem_mismatch.py <path-to-SKILL.md> <path-to-target-repo>",
              file=sys.stderr)
        sys.exit(1)
    skill_md_path, repo_path = sys.argv[1], sys.argv[2]
    repo_ecosystems = detect_repo_ecosystems(repo_path)
    mismatches = find_mismatches(skill_md_path, repo_path)
    print(json.dumps(mismatches, indent=2))
    print(f"\n# Target repo ecosystem(s) detected: {sorted(repo_ecosystems) or 'NONE'}. "
          f"Found {len(mismatches)} hardcoded command(s) that don't match.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
