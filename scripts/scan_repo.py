#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    from detect_stack import detect_stack_from_paths
    from utils import load_ignore_patterns, should_ignore, rel_posix, read_text_limited, is_secret_path, dump_json
except ImportError:
    from .detect_stack import detect_stack_from_paths
    from .utils import load_ignore_patterns, should_ignore, rel_posix, read_text_limited, is_secret_path, dump_json

CFFUNCTION_RE = re.compile(r"<\s*cffunction\b[^>]*\bname\s*=\s*['\"]([^'\"]+)['\"]", re.I)
SCRIPT_FUNCTION_RE = re.compile(
    r"(?im)^\s*(?:(?:public|private|remote|package)\s+)?(?:(?:static|final)\s+)?(?:(?:[A-Za-z_$][\w.$<>\[\],]*|any|void|numeric|string|boolean|query|struct|array)\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("
)

BUCKET_RULES = [
    ("entry_points", ["application.cfc", "application.cfm", "index.cfm", "index.php", "app.py", "manage.py", "server.js", "main.js"]),
    ("routes", ["route", "routes"]),
    ("controllers", ["controller", "controllers"]),
    ("handlers", ["handler", "handlers"]),
    ("services", ["service", "services"]),
    ("repositories", ["repository", "repositories", "dao"]),
    ("models", ["model", "models"]),
    ("entities", ["entity", "entities"]),
    ("components", ["component", "components", ".cfc"]),
    ("views", ["view", "views", "templates"]),
    ("frontend", ["frontend", "client", "assets", ".jsx", ".tsx", ".vue", ".svelte"]),
    ("config", ["config", ".env", "settings", "server.json", "box.json"]),
    ("database", ["database", "db", "schema", "migration", "migrations", "sql"]),
    ("migrations", ["migration", "migrations"]),
    ("tests", ["test", "tests", "spec", "specs"]),
    ("auth_candidates", ["auth", "login", "logout", "permission", "role", "session", "security"]),
    ("permission_candidates", ["permission", "role", "acl", "access"]),
    ("deployment", ["deploy", "docker", "compose", "nginx", "iis"]),
    ("ci_cd", [".github", "workflow", "gitlab-ci", "jenkins", "circleci", "azure-pipelines"]),
    ("docs", ["readme", "docs", "documentation", ".md"]),
]

EVIDENCE_NAMES = {
    "application.cfc", "application.cfm", "box.json", "server.json", "composer.json", "package.json",
    "pyproject.toml", "requirements.txt", "dockerfile", "docker-compose.yml", "compose.yml", "readme.md",
}


def bucket_path(rel: str) -> List[str]:
    low = rel.lower()
    buckets = []
    for bucket, needles in BUCKET_RULES:
        if any(n in low for n in needles):
            buckets.append(bucket)
    return buckets or ["other"]


def extract_cfc_methods(text: str) -> List[str]:
    names = set(CFFUNCTION_RE.findall(text))
    names.update(SCRIPT_FUNCTION_RE.findall(text))
    return sorted(n for n in names if n)


def likely_evidence_file(rel: str) -> bool:
    low = rel.lower()
    name = Path(low).name
    if name in EVIDENCE_NAMES:
        return True
    return any(part in low for part in ["route", "auth", "login", "permission", "session", "database", "db", "schema", "migration", "docker", "deploy", "ci", "workflow", "config", "settings"])


def scan_repository(repo: Path, max_files: int = 20000) -> Dict[str, object]:
    repo = Path(repo).resolve()
    ignores = load_ignore_patterns(repo)
    files: List[str] = []
    dirs: List[str] = []
    ignored: List[str] = []
    buckets: Dict[str, List[str]] = {}
    evidence: Dict[str, str] = {}
    cfc_inventory: List[Dict[str, object]] = []

    for path in repo.rglob("*"):
        rel = rel_posix(path, repo)
        is_dir = path.is_dir()
        if should_ignore(rel, is_dir, ignores):
            ignored.append(rel + ("/" if is_dir else ""))
            continue
        if is_dir:
            dirs.append(rel)
            continue
        files.append(rel)
        for bucket in bucket_path(rel):
            buckets.setdefault(bucket, []).append(rel)
        if len(files) >= max_files:
            break

    # Generated Atlas docs may mention many technologies as false positives.
    # Exclude project-atlas/ from stack detection and evidence reads so validation
    # after generation is stable and based on the actual application repository.
    app_files = [rel for rel in files if not rel.startswith("project-atlas/")]
    stack = detect_stack_from_paths(app_files)

    db_text_fragments = []
    for rel in app_files:
        path = repo / rel
        if rel.lower().endswith(".cfc"):
            if is_secret_path(rel):
                cfc_inventory.append({"path": rel, "methods": [], "status": "secret skipped", "role": infer_role(rel)})
                continue
            text, status = read_text_limited(path, max_bytes=500_000)
            methods = extract_cfc_methods(text) if text else []
            cfc_inventory.append({
                "path": rel,
                "methods": methods,
                "status": status if methods else (status if status != "extracted" else "no methods found"),
                "role": infer_role(rel),
            })
        elif likely_evidence_file(rel) and not is_secret_path(rel):
            text, status = read_text_limited(path, max_bytes=80_000)
            if text:
                evidence[rel] = text[:4000]
                db_text_fragments.append(text.lower())
            else:
                evidence[rel] = f"[{status}]"

    db_text = "\n".join(db_text_fragments)
    if any(token in db_text for token in ["mssql", "sqlsrv", "sql server", "sqlserver", "pdo_sqlsrv", "jtds"]):
        stack["mssql"] = True
    if any(token in db_text for token in ["mysql", "mysqli", "pdo_mysql", "mysqlconnector"]):
        stack["mysql"] = True

    return {
        "repo": str(repo),
        "file_count": len(files),
        "dir_count": len(dirs),
        "files": files,
        "dirs": dirs,
        "buckets": {k: sorted(v)[:200] for k, v in sorted(buckets.items())},
        "ignored_sample": sorted(ignored)[:200],
        "stack": stack,
        "evidence": evidence,
        "cfc_inventory": cfc_inventory,
    }


def infer_role(rel: str) -> str:
    low = rel.lower()
    if "controller" in low:
        return "controller"
    if "service" in low:
        return "service"
    if "model" in low:
        return "model"
    if "dao" in low or "repository" in low:
        return "data access"
    if "handler" in low:
        return "handler"
    if "auth" in low or "login" in low or "security" in low:
        return "auth/security"
    if Path(low).name == "application.cfc":
        return "application entry point"
    return "component"


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan a repository for Project Atlas.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--output")
    args = parser.parse_args()
    data = scan_repository(Path(args.repo), max_files=args.max_files)
    text = dump_json(data)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
