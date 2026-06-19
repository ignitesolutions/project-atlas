#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List

try:
    from utils import load_ignore_patterns, should_ignore, rel_posix, dump_json
except ImportError:
    from .utils import load_ignore_patterns, should_ignore, rel_posix, dump_json


def iter_files(repo: Path) -> Iterable[str]:
    ignores = load_ignore_patterns(repo)
    for path in repo.rglob("*"):
        rel = rel_posix(path, repo)
        if should_ignore(rel, path.is_dir(), ignores):
            if path.is_dir():
                continue
            continue
        if path.is_file():
            yield rel


def detect_stack_from_paths(paths: Iterable[str]) -> Dict[str, object]:
    files = list(paths)
    lower = [p.lower() for p in files]

    def any_name(*names: str) -> bool:
        names_l = {n.lower() for n in names}
        return any(Path(p).name.lower() in names_l for p in files)

    def any_suffix(*suffixes: str) -> bool:
        return any(p.endswith(s.lower()) for p in lower for s in suffixes)

    def any_contains(*parts: str) -> bool:
        return any(any(part.lower() in p for part in parts) for p in lower)

    stack = {
        "cfml": any_suffix(".cfm", ".cfc") or any_name("Application.cfc", "Application.cfm", "box.json", "server.json"),
        "php": any_suffix(".php") or any_name("composer.json", "artisan", "wp-config.php"),
        "node-js": any_name("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "vite.config.js", "next.config.js", "nuxt.config.js", "webpack.config.js"),
        "python": any_name("pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock", "manage.py", "app.py", "wsgi.py", "asgi.py"),
        "docker": any_name("Dockerfile", "docker-compose.yml", "compose.yml", ".dockerignore") or any_contains("docker/"),
        "mysql": any_contains("mysql", "mysqli", "pdo_mysql", "mysqlconnector"),
        "mssql": any_contains("mssql", "sqlserver", "sql server", "sqlsrv", "pdo_sqlsrv", "jtds"),
        "markers": sorted([p for p in files if Path(p).name in {"Application.cfc", "Application.cfm", "box.json", "server.json", "composer.json", "package.json", "pyproject.toml", "requirements.txt", "Dockerfile", "docker-compose.yml", "compose.yml"}]),
    }
    return stack


def detect_stack(repo: Path) -> Dict[str, object]:
    return detect_stack_from_paths(iter_files(repo))


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect Project Atlas repository stack.")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    print(dump_json(detect_stack(repo)))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
