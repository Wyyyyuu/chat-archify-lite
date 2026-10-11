#!/usr/bin/env python3
"""Build and test the fictional one-conversation Chat Archify Lite demo."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MIN_PYTHON = (3, 9)
TESTED_ARCHIFY = "2.17.0-dev.1"


def run(label: str, command: list[object], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"\n== {label} ==", flush=True)
    run_env = (env or os.environ).copy()
    run_env["PYTHONDONTWRITEBYTECODE"] = "1"
    run_env["PYTHONUTF8"] = "1"
    result = subprocess.run([str(part) for part in command], cwd=str(cwd), text=True,
                            encoding="utf-8", capture_output=True, env=run_env)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if result.returncode:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}; no current demo was reported.")


def check_environment(archify_dir: Path) -> tuple[str, str]:
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError(f"Python 3.9 or newer is required; found {sys.version.split()[0]}.")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js 18 or newer is required to run Archify; install it separately and put node on PATH.")
    version = subprocess.run([node, "--version"], text=True, encoding="utf-8", capture_output=True)
    if version.returncode:
        raise RuntimeError("Could not read the Node.js version: " + version.stderr.strip())
    try:
        major = int(version.stdout.strip().lstrip("v").split(".")[0])
    except (ValueError, IndexError):
        raise RuntimeError("Could not parse Node.js version: " + version.stdout.strip()) from None
    if major < 18:
        raise RuntimeError(f"Node.js 18 or newer is required; found {version.stdout.strip()}.")
    if not archify_dir.is_dir() or not (archify_dir / "bin" / "archify.mjs").is_file():
        raise RuntimeError("--archify-dir must be the separately installed Archify skill directory containing bin/archify.mjs.")
    installed = "unknown"
    try:
        installed = json.loads((archify_dir / "package.json").read_text(encoding="utf-8")).get("version", "unknown")
    except (OSError, json.JSONDecodeError):
        pass
    print(f"Python {sys.version.split()[0]} | Node.js {version.stdout.strip()} | Archify {installed}")
    if installed != TESTED_ARCHIFY:
        print(f"Compatibility note: this integration was tested with Archify {TESTED_ARCHIFY}; verify other versions.", file=sys.stderr)
    return node, installed


def build(archify_dir: Path, out_dir: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    example = root / "examples" / "interactive-demo"
    archify_dir = archify_dir.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    node, _installed = check_environment(archify_dir)
    inputs = out_dir / "source"
    inputs.mkdir(parents=True, exist_ok=True)
    shutil.copytree(example, inputs, dirs_exist_ok=True)
    spec, viewer, manifest = inputs / "workflow-v2.json", inputs / "archify-overview.html", inputs / "manifest.json"
    packaged = out_dir / "chat-archify-lite-demo.html"
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="chat-archify-tmp-", dir=str(out_dir)) as temp_dir:
        archify_env = os.environ.copy()
        archify_env["TEMP"] = temp_dir
        archify_env["TMP"] = temp_dir
        run("Archify showcase validation", [node, archify_dir / "bin" / "archify.mjs", "validate", "workflow", spec, "--quality", "showcase", "--json"], archify_dir, archify_env)
        run("Archify delivery", [node, archify_dir / "bin" / "archify.mjs", "deliver", "workflow", spec, viewer, "--quality", "showcase", "--json"], archify_dir, archify_env)
    run("All-route geometry check", [sys.executable, root / "scripts" / "check_routes.py", viewer], root)
    run("Lite attachment packaging", [sys.executable, root / "scripts" / "lite_package.py", manifest, packaged], root)
    run("Lite limits, topology, and byte checks", [sys.executable, root / "tests" / "test_lite_package.py", "--example-dir", inputs], root)
    run("Lite portable navigation smoke test", [node, root / "tests" / "lite-navigation.cjs", packaged], root)
    print(f"\nComplete Lite demo: {packaged}", flush=True)
    return packaged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archify-dir", required=True, type=Path, help="Separately installed Archify skill directory containing bin/archify.mjs")
    parser.add_argument("--out-dir", required=True, type=Path, help="Directory for copied fictional inputs and final Lite HTML")
    args = parser.parse_args()
    try:
        build(args.archify_dir, args.out_dir)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Chat Archify Lite demo was not completed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
