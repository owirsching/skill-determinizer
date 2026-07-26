#!/usr/bin/env python3
"""
Scan a SKILL.md (or any markdown instructions file) for vague / underspecified
language that could plausibly be replaced with a deterministic command,
exact path, exact value, or explicit decision table.

Usage:
    python3 scan_vague_language.py <path-to-SKILL.md>

Output: JSON list of {line_number, line_text, category, matched_phrase}
Categories are a starting point, not gospel -- always eyeball the results,
since plenty of matches will be false positives (e.g. "clean up" inside a
already-precise `rm -rf ./tmp/$RUN_ID/` line shouldn't be re-flagged).
"""
import sys
import re
import json

# Each category maps to a regex (case-insensitive) and a short reason,
# describing WHY this phrase-class tends to hide non-determinism.
CATEGORIES = {
    "hedge_adjective": {
        "pattern": r"\b(appropriate(?:ly)?|sensible|reasonable|proper(?:ly)?|suitable|good\b|nice\b|clean(?:ly)?)\b",
        "reason": "Quality adjective with no measurable definition -- reader has to guess what counts.",
    },
    "vague_quantifier": {
        "pattern": r"\b(some|a few|several|many|enough|as needed|as necessary|if needed|if necessary)\b",
        "reason": "Unspecified amount or condition -- no exact number/threshold given.",
    },
    "vague_naming": {
        "pattern": r"\b(descriptive name|meaningful name|good (?:name|message)|name it (?:something|appropriately))\b",
        "reason": "Naming left to judgment -- needs an explicit template/convention.",
    },
    "ambiguous_action_verb": {
        "pattern": r"\b(set up|handle|deal with|take care of|make sure (?:it'?s|that|to)|figure out|sort out)\b",
        "reason": "Verb describes an outcome, not a step -- likely hides an exact command sequence.",
    },
    "vague_location": {
        "pattern": r"\b(somewhere sensible|the right place|an appropriate (?:location|folder|directory|place))\b",
        "reason": "No exact path given.",
    },
    "vague_format": {
        "pattern": r"\b(nicely formatted|in a good format|readable format|the usual format)\b",
        "reason": "No exact template/schema given.",
    },
    "vague_condition": {
        "pattern": r"\b(if applicable|where applicable|when relevant|as relevant|use (?:your|good) judgment)\b",
        "reason": "Condition for branching isn't spelled out -- needs an explicit if/then rule.",
    },
    "vague_check": {
        "pattern": r"\b(check (?:that|if) it works|verify it'?s correct|make sure it'?s valid|confirm (?:it'?s|everything is) (?:working|correct|fine))\b",
        "reason": "Validation step described qualitatively -- needs an exact check (exit code, schema validation, etc).",
    },
    "environment_task": {
        "pattern": r"\b(run (?:the )?(?:unit )?tests|run the linter|run lint|build the project|install (?:the )?dependencies|start the (?:dev(?:elopment)? )?server|typecheck|type[- ]check|open (?:a |the )?(?:PR|pull request)|create (?:a |the )?(?:PR|pull request)|submit (?:a |the )?(?:PR|pull request))\b",
        "reason": "This task's exact command depends on the repo's own tooling -- don't guess a generic default (e.g. `pytest`, or assuming the `gh` CLI is installed and authenticated for PR creation), discover what this repo/environment actually supports (see scripts/discover_environment_commands.py).",
    },
}


def scan(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    results = []
    for i, line in enumerate(lines, start=1):
        for category, spec in CATEGORIES.items():
            for m in re.finditer(spec["pattern"], line, flags=re.IGNORECASE):
                results.append({
                    "line_number": i,
                    "line_text": line.rstrip("\n"),
                    "category": category,
                    "matched_phrase": m.group(0),
                    "reason": spec["reason"],
                })
    return results


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scan_vague_language.py <path-to-SKILL.md>", file=sys.stderr)
        sys.exit(1)

    results = scan(sys.argv[1])
    print(json.dumps(results, indent=2))
    print(f"\n# Found {len(results)} candidate phrase(s) across "
          f"{len(set(r['line_number'] for r in results))} line(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
