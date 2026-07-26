#!/usr/bin/env python3
"""
Discover the ACTUAL commands a repo already uses for common tasks --
test, build, lint, format, typecheck, install, dev server -- instead of
guessing a generic default like `pytest -x -q` or `npm test`.

The whole point: "run the unit tests" should become whatever *this*
project already runs, not a plausible-sounding guess. This script reads
the repo's own config/manifests/CI files and reports what it finds, with
provenance, so the calling skill can turn "run unit tests" into the exact
discovered command and then verify it actually works.

Usage:
    python3 discover_environment_commands.py <path-to-repo-root>

Output: JSON: {task: [{"command": ..., "source": ..., "confidence": ...}]}
Multiple entries under one task = conflicting sources -- the calling
skill should surface this and ask the user which is authoritative rather
than silently picking one.
"""
import sys
import os
import re
import json

TASKS = ["test", "build", "lint", "format", "typecheck", "install", "dev"]

# Node/npm-style script keys that map to each task (package.json "scripts")
NPM_SCRIPT_ALIASES = {
    "test": ["test", "test:unit", "unit"],
    "build": ["build"],
    "lint": ["lint"],
    "format": ["format", "fmt"],
    "typecheck": ["typecheck", "type-check", "tsc"],
    "dev": ["dev", "start"],
}

# Makefile target names that map to each task
MAKE_TARGET_ALIASES = {
    "test": ["test", "tests", "unit-test", "unittest"],
    "build": ["build"],
    "lint": ["lint"],
    "format": ["format", "fmt"],
    "typecheck": ["typecheck", "type-check"],
    "install": ["install", "setup", "deps"],
    "dev": ["dev", "run", "serve"],
}


def detect_node_package_manager(repo):
    if os.path.exists(os.path.join(repo, "pnpm-lock.yaml")):
        return "pnpm"
    if os.path.exists(os.path.join(repo, "yarn.lock")):
        return "yarn"
    if os.path.exists(os.path.join(repo, "package-lock.json")):
        return "npm"
    if os.path.exists(os.path.join(repo, "package.json")):
        return "npm"  # default fallback
    return None


def run_script_command(pm, script_name):
    if pm == "yarn":
        return f"yarn {script_name}"
    if pm == "pnpm":
        return f"pnpm run {script_name}"
    return f"npm run {script_name}"


def scan_package_json(repo, results):
    path = os.path.join(repo, "package.json")
    if not os.path.exists(path):
        return
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        return
    scripts = data.get("scripts", {})
    pm = detect_node_package_manager(repo)
    for task, aliases in NPM_SCRIPT_ALIASES.items():
        for alias in aliases:
            if alias in scripts:
                results.setdefault(task, []).append({
                    "command": run_script_command(pm, alias),
                    "source": f"package.json scripts.{alias}",
                    "raw": scripts[alias],
                    "confidence": "high",
                })
                break  # only take the first matching alias per file


def scan_makefile(repo, results):
    path = None
    for candidate in ["Makefile", "makefile", "GNUmakefile"]:
        p = os.path.join(repo, candidate)
        if os.path.exists(p):
            path = p
            break
    if not path:
        return
    try:
        with open(path) as f:
            lines = f.readlines()
    except Exception:
        return
    target_pattern = re.compile(r"^([a-zA-Z0-9_.\-]+):")
    targets = set()
    for line in lines:
        m = target_pattern.match(line)
        if m and not line.startswith("\t"):
            targets.add(m.group(1))
    for task, aliases in MAKE_TARGET_ALIASES.items():
        for alias in aliases:
            if alias in targets:
                results.setdefault(task, []).append({
                    "command": f"make {alias}",
                    "source": f"Makefile target '{alias}'",
                    "confidence": "high",
                })
                break


def scan_python_config(repo, results):
    # pytest config presence -> test task
    for candidate in ["pytest.ini", "tox.ini", "setup.cfg"]:
        p = os.path.join(repo, candidate)
        if os.path.exists(p):
            results.setdefault("test", []).append({
                "command": "pytest",
                "source": f"presence of {candidate} (pytest config)",
                "confidence": "medium",
            })
            break
    pyproject = os.path.join(repo, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject) as f:
                content = f.read()
        except Exception:
            content = ""
        if "[tool.pytest" in content:
            results.setdefault("test", []).append({
                "command": "pytest",
                "source": "pyproject.toml [tool.pytest.ini_options]",
                "confidence": "high",
            })
        if "[tool.ruff]" in content:
            results.setdefault("lint", []).append({
                "command": "ruff check .",
                "source": "pyproject.toml [tool.ruff]",
                "confidence": "high",
            })
        if "[tool.black]" in content:
            results.setdefault("format", []).append({
                "command": "black .",
                "source": "pyproject.toml [tool.black]",
                "confidence": "high",
            })
        if "[tool.mypy]" in content:
            results.setdefault("typecheck", []).append({
                "command": "mypy .",
                "source": "pyproject.toml [tool.mypy]",
                "confidence": "high",
            })
        # Poetry: check for the actual [tool.poetry] section header, not a
        # bare substring match against the whole file -- "poetry" can
        # appear in a comment, an author bio, or an unrelated dependency
        # name (e.g. a poetry-plugin-*) without the project actually being
        # Poetry-managed. Section-header presence is the real signal.
        if "[tool.poetry]" in content:
            results.setdefault("install", []).append({
                "command": "poetry install",
                "source": "pyproject.toml [tool.poetry]",
                "confidence": "high",
            })
        elif os.path.exists(os.path.join(repo, "uv.lock")):
            # uv.lock is unambiguous -- only uv creates/reads it.
            results.setdefault("install", []).append({
                "command": "uv sync",
                "source": "uv.lock present",
                "confidence": "high",
            })
        elif "[build-system]" in content:
            # Some PEP 517 backend is declared (hatchling, flit_core,
            # setuptools, etc.) but not one with a distinctive lockfile.
            # `pip install -e .` is the generic fallback that works across
            # these backends -- lower confidence than the two checks above
            # since it's a fallback, not a tool-specific command, and the
            # calling skill should still verify it actually works for this
            # repo before writing it into a SKILL.md.
            backend_match = re.search(r'build-backend\s*=\s*"([^"]+)"', content)
            backend = backend_match.group(1) if backend_match else "unknown"
            results.setdefault("install", []).append({
                "command": "pip install -e .",
                "source": f"pyproject.toml [build-system] (backend: {backend})",
                "confidence": "medium",
            })

    if os.path.exists(os.path.join(repo, "requirements.txt")):
        results.setdefault("install", []).append({
            "command": "pip install -r requirements.txt",
            "source": "requirements.txt present",
            "confidence": "medium",
        })
    if os.path.exists(os.path.join(repo, "Pipfile")):
        results.setdefault("install", []).append({
            "command": "pipenv install",
            "source": "Pipfile present",
            "confidence": "high",
        })


def scan_jvm_config(repo, results):
    """Gradle and Maven -- JVM/Kotlin/Java repos, which the rest of this
    script previously had no coverage for at all (it only knew Node and
    Python). Without this, a Kotlin repo produces zero discovered
    commands, and a calling skill has nothing to fall back on except a
    guess -- often the wrong one, since guides/examples online skew
    heavily toward npm/pytest phrasing."""
    has_gradle = any(os.path.exists(os.path.join(repo, f))
                      for f in ("build.gradle", "build.gradle.kts"))
    if has_gradle:
        # Prefer the wrapper script over a bare `gradle` binary -- the
        # wrapper pins the exact Gradle version the project expects,
        # whereas a global `gradle` install may be a different version
        # entirely and behave differently.
        wrapper = "./gradlew" if os.path.exists(os.path.join(repo, "gradlew")) else "gradle"
        results.setdefault("test", []).append({
            "command": f"{wrapper} test",
            "source": "build.gradle(.kts) present",
            "confidence": "high",
        })
        results.setdefault("build", []).append({
            "command": f"{wrapper} build",
            "source": "build.gradle(.kts) present",
            "confidence": "high",
        })
        try:
            build_file = "build.gradle.kts" if os.path.exists(os.path.join(repo, "build.gradle.kts")) else "build.gradle"
            with open(os.path.join(repo, build_file)) as f:
                build_content = f.read()
        except Exception:
            build_content = ""
        # Lint/format plugins vary by project -- only report one if we can
        # actually see the plugin declared, rather than guessing a default.
        if "detekt" in build_content:
            results.setdefault("lint", []).append({
                "command": f"{wrapper} detekt",
                "source": f"{build_file} (detekt plugin detected)",
                "confidence": "high",
            })
        if "ktlint" in build_content:
            results.setdefault("format", []).append({
                "command": f"{wrapper} ktlintCheck",
                "source": f"{build_file} (ktlint plugin detected)",
                "confidence": "high",
            })
        # Gradle resolves dependencies as part of build/test rather than
        # via a separate install step -- deliberately not reporting an
        # "install" task here rather than inventing one that doesn't map
        # to anything real.

    if os.path.exists(os.path.join(repo, "pom.xml")):
        results.setdefault("test", []).append({
            "command": "mvn test",
            "source": "pom.xml present",
            "confidence": "high",
        })
        results.setdefault("build", []).append({
            "command": "mvn package",
            "source": "pom.xml present",
            "confidence": "high",
        })


def scan_ci_workflows(repo, results):
    """Lower-confidence corroborating evidence only -- CI config often has
    extra flags (coverage, parallelism) irrelevant to local dev, so this is
    never taken as the sole source without a script/Makefile match too."""
    workflows_dir = os.path.join(repo, ".github", "workflows")
    if not os.path.isdir(workflows_dir):
        return
    keyword_task_map = {
        "pytest": "test", "npm test": "test", "npm run test": "test",
        "make test": "test", "eslint": "lint", "ruff": "lint",
        "npm run build": "build", "make build": "build",
        "mypy": "typecheck", "tsc": "typecheck",
        "gradlew test": "test", "gradle test": "test",
        "mvn test": "test", "gradlew build": "build", "mvn package": "build",
    }
    for fname in os.listdir(workflows_dir):
        if not (fname.endswith(".yml") or fname.endswith(".yaml")):
            continue
        try:
            with open(os.path.join(workflows_dir, fname)) as f:
                content = f.read()
        except Exception:
            continue
        for keyword, task in keyword_task_map.items():
            if keyword in content:
                results.setdefault(task, []).append({
                    "command": keyword,
                    "source": f".github/workflows/{fname} (CI step mentions '{keyword}')",
                    "confidence": "low",
                })


def discover(repo):
    results = {}
    scan_package_json(repo, results)
    scan_makefile(repo, results)
    scan_python_config(repo, results)
    scan_jvm_config(repo, results)
    scan_ci_workflows(repo, results)

    # Flag conflicts: >1 distinct command for the same task from
    # medium/high-confidence sources
    for task, entries in results.items():
        distinct_commands = {e["command"] for e in entries if e["confidence"] != "low"}
        if len(distinct_commands) > 1:
            for e in entries:
                e["conflict"] = True
    return results


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 discover_environment_commands.py <path-to-repo-root>", file=sys.stderr)
        sys.exit(1)
    repo = sys.argv[1]
    results = discover(repo)
    print(json.dumps(results, indent=2))
    if not results:
        print("\n# No task commands discovered from config/manifests/CI. "
              "Ask the user directly rather than guessing a generic default.",
              file=sys.stderr)
    else:
        conflicts = [t for t, entries in results.items()
                     if any(e.get("conflict") for e in entries)]
        if conflicts:
            print(f"\n# Conflicting sources found for: {', '.join(conflicts)} "
                  f"-- ask the user which is authoritative.", file=sys.stderr)


if __name__ == "__main__":
    main()
