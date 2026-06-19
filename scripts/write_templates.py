#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from scan_repo import scan_repository
    from utils import (
        EXISTING_REQUIRED_FILES, EXISTING_REQUIRED_DIRS, PLATFORM_FILE_MAP,
        FORBIDDEN_GENERATED_PATHS, ALIAS_FILES, append_log, detect_required_platforms,
        dump_json, now_iso, verify_existing_atlas, write_file,
        ROOT_GENERATED_FILES
    )
except ImportError:
    from .scan_repo import scan_repository
    from .utils import (
        EXISTING_REQUIRED_FILES, EXISTING_REQUIRED_DIRS, PLATFORM_FILE_MAP,
        FORBIDDEN_GENERATED_PATHS, ALIAS_FILES, append_log, detect_required_platforms,
        dump_json, now_iso, verify_existing_atlas, write_file,
        ROOT_GENERATED_FILES
    )


def bullet(items: Iterable[str], limit: int = 50) -> str:
    items = list(items)[:limit]
    if not items:
        return "- none detected\n"
    return "".join(f"- `{item}`\n" for item in items)


def table(rows: List[List[str]], headers: List[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(str(c).replace("\n", "<br>") for c in row) + " |")
    return "\n".join(out) + "\n"


def stack_lines(stack: Dict[str, Any]) -> str:
    rows = []
    for key in ["cfml", "php", "node-js", "python", "mysql", "mssql", "docker"]:
        rows.append([key, "yes" if stack.get(key) else "no"])
    return table(rows, ["Platform", "Detected"])


def cfc_inventory_markdown(scan: Dict[str, Any]) -> str:
    cfc_items = scan.get("cfc_inventory", []) or []
    if not cfc_items:
        return "No `.cfc` files detected.\n"
    rows = []
    for item in cfc_items:
        methods = item.get("methods") or []
        method_text = ", ".join(f"`{m}`" for m in methods) if methods else "_none listed_"
        rows.append([item.get("path", ""), item.get("role", "component"), method_text, item.get("status", "unknown")])
    return table(rows, ["CFC", "Likely role", "Functions / methods", "Extraction status"])


def cfc_index_content(scan: Dict[str, Any]) -> str:
    cfc_items = scan.get("cfc_inventory", []) or []
    if not cfc_items:
        return ""
    return f"""
# CFML Component / Method Index

This optional generated index supports `code-map.md` and `platforms/cfml.md`. It does not replace them.

{cfc_inventory_markdown(scan)}
"""



# ---------------------------------------------------------------------------
# Root file generation (CLAUDE.md and AGENTS.md at the repository root)
# ---------------------------------------------------------------------------

_ATLAS_SECTION_START = "<!-- project-atlas:start -->"
_ATLAS_SECTION_END   = "<!-- project-atlas:end -->"


def _claude_md_section(repo_name: str) -> str:
    return f"""{_ATLAS_SECTION_START}
## Project Atlas — Claude Code instructions

This repository uses **Project Atlas** for AI-readable project context.

### Required reading at every session start

Before writing or editing any code, read these files:

1. `project-atlas/agent-playbook.md` — rules, conventions, and what to update
2. `project-atlas/project-overview.md` — what this project does
3. `project-atlas/stack.md` — languages, frameworks, and infrastructure
4. `project-atlas/known-risks.md` — fragile areas; do not break these

### After every task

Check whether code, architecture, auth, database, deployment, or features changed durably.
If yes, update the relevant Atlas files and append `project-atlas/maintenance-log.md`.
Follow the table in `project-atlas/agent-playbook.md` to know which file to update.

Do not update Atlas for formatting-only, comment-only, debug, or reverted changes.
{_ATLAS_SECTION_END}
"""


def _agents_md_section(repo_name: str) -> str:
    return f"""{_ATLAS_SECTION_START}
## Project Atlas — Agent instructions

This repository uses **Project Atlas** for AI-readable project context.

### Required reading at every session start

Before writing or editing any code, read these files:

1. `project-atlas/agent-playbook.md` — rules, conventions, and what to update
2. `project-atlas/project-overview.md` — what this project does
3. `project-atlas/stack.md` — languages, frameworks, and infrastructure
4. `project-atlas/known-risks.md` — fragile areas; do not break these

### After every task

Check whether code, architecture, auth, database, deployment, or features changed durably.
If yes, update the relevant Atlas files and append `project-atlas/maintenance-log.md`.
Follow the table in `project-atlas/agent-playbook.md` to know which file to update.

Do not update Atlas for formatting-only, comment-only, debug, or reverted changes.
{_ATLAS_SECTION_END}
"""


_ROOT_SECTIONS = {
    "CLAUDE.md": _claude_md_section,
    "AGENTS.md": _agents_md_section,
}


def write_root_agent_file(path: Path, repo_name: str, created: list, updated: list, skipped: list) -> None:
    """Create or update CLAUDE.md / AGENTS.md with our Project Atlas section.

    - File absent  → create it containing just our section.
    - File present, section absent  → append our section.
    - File present, section present → replace our section in-place.
    """
    fn = path.name
    section_fn = _ROOT_SECTIONS.get(fn)
    if section_fn is None:
        return
    section = section_fn(repo_name).strip() + "\n"

    if not path.exists():
        path.write_text(section, encoding="utf-8")
        created.append(path)
        return

    existing = path.read_text(encoding="utf-8", errors="ignore")
    if _ATLAS_SECTION_START in existing and _ATLAS_SECTION_END in existing:
        # Replace existing section
        before = existing[:existing.index(_ATLAS_SECTION_START)]
        after  = existing[existing.index(_ATLAS_SECTION_END) + len(_ATLAS_SECTION_END):]
        new_text = before + section + after.lstrip("\n")
        if new_text != existing:
            path.write_text(new_text, encoding="utf-8")
            updated.append(path)
        else:
            skipped.append(path)
    else:
        # Append our section
        new_text = existing.rstrip() + "\n\n" + section
        path.write_text(new_text, encoding="utf-8")
        updated.append(path)


def existing_contents(scan: Dict[str, Any]) -> Dict[str, str]:
    stack = scan.get("stack", {}) or {}
    buckets = scan.get("buckets", {}) or {}
    repo_name = Path(scan.get("repo", ".")).name
    generated = now_iso()
    markers = stack.get("markers", []) or []

    code_map = f"""
# Code Map

Generated: {generated}

## Repository shape

- Files scanned: {scan.get('file_count', 0)}
- Directories scanned: {scan.get('dir_count', 0)}

## Key paths by bucket

### Entry points
{bullet(buckets.get('entry_points', []))}
### Routes
{bullet(buckets.get('routes', []))}
### Controllers
{bullet(buckets.get('controllers', []))}
### Handlers
{bullet(buckets.get('handlers', []))}
### Services
{bullet(buckets.get('services', []))}
### Repositories / data access
{bullet(buckets.get('repositories', []))}
### Models / entities / components
{bullet((buckets.get('models', []) + buckets.get('entities', []) + buckets.get('components', [])))}

## CFML component inventory

When `.cfc` files are present, this section must list every discovered component. A longer generated copy may also be available in `cfc-index.md`, but this section remains authoritative for verification.

{cfc_inventory_markdown(scan)}
"""

    contents = {
        "README.md": f"""
# Project Atlas

This folder contains AI-readable project context for `{repo_name}`.

## Start here

1. Read `agent-playbook.md`.
2. Read `project-overview.md`, `stack.md`, and `architecture.md`.
3. Use `code-map.md`, `feature-index.md`, `database.md`, and `auth-and-access.md` before changing code.
4. Append meaningful updates to `maintenance-log.md` after durable project changes.

Generated: {generated}
""",
        "agent-playbook.md": """
# Agent Playbook

## Rules

- Keep changes small and verify them.
- Read the relevant Atlas files before editing code.
- Update Atlas only for durable project knowledge.
- Do not store secrets.
- Do not update Atlas for formatting-only, comment-only, debug, or reverted changes.

## Before every task

1. Read `project-atlas/project-overview.md`, `project-atlas/stack.md`, and `project-atlas/architecture.md`.
2. Check `project-atlas/known-risks.md` for fragile areas.
3. Check `project-atlas/open-questions.md` for unresolved decisions that may affect the task.
4. Check `project-atlas/code-map.md` for likely files to read or edit.

## After every task

Review whether any of the following changed durably. If yes, update the relevant Atlas file and append a dated entry to `project-atlas/maintenance-log.md`.

| What changed | Update this file |
|---|---|
| Features added, moved, or removed | `project-atlas/feature-index.md` |
| Routes, services, components, or entry points | `project-atlas/code-map.md` |
| Auth, sessions, permissions, or access control | `project-atlas/auth-and-access.md` |
| Schema, migrations, or query patterns | `project-atlas/database.md` |
| Runtimes, frameworks, or dependencies | `project-atlas/stack.md` and `project-atlas/dependency-map.md` |
| Build, deploy, hosting, Docker, or CI | `project-atlas/deployment.md` |
| Fragile, security-sensitive, or risky areas | `project-atlas/known-risks.md` |
| Coding conventions or patterns established | `project-atlas/conventions.md` |

If nothing changed durably, do not update Atlas.
""",
        "project-overview.md": f"""
# Project Overview

Project root scanned: `{scan.get('repo', '.')}`

## Current understanding

Project purpose was not inferred with high confidence from filenames alone. Review application docs and update this file with confirmed business context.

## Evidence markers
{bullet(markers)}
""",
        "stack.md": f"""
# Stack

{stack_lines(stack)}

## Markers
{bullet(markers)}
""",
        "architecture.md": f"""
# Architecture

Generated: {generated}

## Detected architecture shape

- CFML/Lucee-style application: {'yes' if stack.get('cfml') else 'no'}
- PHP application: {'yes' if stack.get('php') else 'no'}
- Node/JavaScript application: {'yes' if stack.get('node-js') else 'no'}
- Python application: {'yes' if stack.get('python') else 'no'}
- Database indicators: {'MSSQL ' if stack.get('mssql') else ''}{'MySQL' if stack.get('mysql') else ''}

## Entry points
{bullet(buckets.get('entry_points', []))}

## Application boundaries

### Controllers / routes / handlers
{bullet((buckets.get('controllers', []) + buckets.get('routes', []) + buckets.get('handlers', [])), limit=100)}
### Services / data access / components
{bullet((buckets.get('services', []) + buckets.get('repositories', []) + buckets.get('components', [])), limit=120)}

## Notes

This file must not remain as a generic scaffold. Refine it when architecture, deployment boundaries, or major feature areas become clearer.
""",
        "code-map.md": code_map,
        "feature-index.md": f"""
# Feature Index

No complete feature catalog was inferred automatically. Use the path buckets below as starting points.

## Candidate feature-related files
{bullet((buckets.get('controllers', []) + buckets.get('handlers', []) + buckets.get('views', []) + buckets.get('routes', [])), limit=120)}
""",
        "database.md": f"""
# Database

## Detected database indicators

- MySQL: {'yes' if stack.get('mysql') else 'no'}
- MSSQL: {'yes' if stack.get('mssql') else 'no'}

## Candidate database files
{bullet((buckets.get('database', []) + buckets.get('migrations', [])), limit=120)}

## Secret handling

Connection values are not stored here. Document variable names and access patterns only.
""",
        "auth-and-access.md": f"""
# Auth and Access

## Candidate auth/access files
{bullet((buckets.get('auth_candidates', []) + buckets.get('permission_candidates', [])), limit=120)}

## Notes

Confirm session, role, permission, and gated access behavior before making auth changes.
""",
        "conventions.md": """
# Conventions

## Coding conventions

Not fully inferred. Add confirmed naming, formatting, routing, database, and testing conventions here.

## Documentation conventions

- Keep Atlas entries concise.
- Prefer paths and durable facts over speculation.
- Mark uncertainty explicitly.
""",
        "dependency-map.md": f"""
# Dependency Map

## Dependency markers
{bullet([p for p in markers if Path(p).name.lower() in {'box.json','server.json','composer.json','package.json','pyproject.toml','requirements.txt'}])}

## Notes

Record important runtime and package dependencies here after reviewing manifests.
""",
        "testing.md": f"""
# Testing

## Candidate test files/directories
{bullet(buckets.get('tests', []), limit=120)}

## Notes

Document how to run tests once confirmed.
""",
        "deployment.md": f"""
# Deployment

## Candidate deployment and CI/CD files
{bullet((buckets.get('deployment', []) + buckets.get('ci_cd', [])), limit=120)}

## Notes

Document environments, build steps, hosting, CI/CD, and rollback processes only after confirmation.
""",
        "known-risks.md": """
# Known Risks

## Current risks

- Automated Atlas generation is based on static repository inspection.
- Review generated summaries before relying on them for production changes.
- Secret values are intentionally excluded.
""",
        "glossary.md": """
# Glossary

Add project-specific terms, acronyms, domain concepts, and internal names here.
""",
        "open-questions.md": """
# Open Questions

- What is the confirmed product/business purpose of this repository?
- What are the authoritative test and deployment commands?
- Which auth and permission paths are security-critical?
""",
        "maintenance-log.md": f"""
# Maintenance Log

## {generated} - Atlas bootstrap

- Created or checked required Project Atlas structure.
- Files scanned: {scan.get('file_count', 0)}
- Verification result is recorded by the bootstrap command output.
""",
        ".project-atlasignore": """
# Paths ignored by Project Atlas scanning
.git/
node_modules/
vendor/
venv/
.venv/
__pycache__/
dist/
build/
coverage/
.cache/
.next/
.nuxt/
target/
bin/
obj/
WEB-INF/lucee/
project-atlas/snapshots/generated/
.env
.env.*
*.pem
*.key
*.p12
*.pfx
""",
        "decisions/README.md": """
# Architecture Decisions

This is an intentional scaffold folder. Create durable decision records here using names like `0001-use-x-for-y.md`.
""",
        "handoffs/README.md": """
# Handoffs

This is an intentional scaffold folder. Create handoff notes here when future agents need continuation context.
""",
        "snapshots/README.md": """
# Snapshots

This is an intentional scaffold folder. Store lightweight project snapshots here when useful. Do not store generated indexes or secrets.
""",
    }
    return contents


def platform_contents(platform: str, scan: Dict[str, Any]) -> str:
    stack = scan.get("stack", {}) or {}
    buckets = scan.get("buckets", {}) or {}
    generated = now_iso()
    if platform == "cfml":
        return f"""
# CFML Platform Notes

Generated: {generated}

## CFML indicators

- CFML detected: {'yes' if stack.get('cfml') else 'no'}

## CFC inventory

This file mirrors the required CFC coverage and may reference `../cfc-index.md` for the generated full index.

{cfc_inventory_markdown(scan)}

## CFML files
{bullet([p for p in scan.get('files', []) if p.lower().endswith(('.cfc', '.cfm'))], limit=200)}
"""
    if platform == "mssql":
        return f"""# MSSQL Platform Notes\n\nMSSQL indicators were detected. Confirm connection libraries, schema ownership, migrations, and deployment process.\n\n## Candidate database files\n{bullet((buckets.get('database', []) + buckets.get('migrations', [])), limit=120)}\n"""
    if platform == "mysql":
        return f"""# MySQL Platform Notes\n\nMySQL indicators were detected. Confirm connection libraries, schema ownership, migrations, and deployment process.\n\n## Candidate database files\n{bullet((buckets.get('database', []) + buckets.get('migrations', [])), limit=120)}\n"""
    if platform == "docker":
        return f"""# Docker Platform Notes\n\nDocker indicators were detected.\n\n## Candidate Docker/deployment files\n{bullet(buckets.get('deployment', []), limit=120)}\n"""
    return f"# {platform} Platform Notes\n\nDetected platform file for `{platform}`. Add confirmed implementation details here.\n"


def create_existing(repo: Path, scan: Dict[str, Any], force: bool = False, backup: bool = False, selected_platforms: Iterable[str] = ()) -> Dict[str, Any]:
    repo_name = Path(scan.get("repo", str(repo))).name
    created: List[Path] = []
    skipped: List[Path] = []
    updated: List[Path] = []
    backed_up: List[Path] = []

    # ── Directories ──────────────────────────────────────────────────────────
    for d in EXISTING_REQUIRED_DIRS:
        (repo / d).mkdir(parents=True, exist_ok=True)

    # ── Required Atlas files ─────────────────────────────────────────────────
    contents = existing_contents(scan)
    for rel in EXISTING_REQUIRED_FILES:
        sub = rel.replace("project-atlas/", "")
        file_content = contents.get(sub, f"# {Path(sub).stem.replace('-', ' ').title()}\n\nGenerated placeholder. Update with confirmed project context.\n")
        write_file(repo / rel, file_content, force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)

    # ── Optional CFML index ──────────────────────────────────────────────────
    if scan.get("cfc_inventory"):
        write_file(repo / "project-atlas/cfc-index.md", cfc_index_content(scan), force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)

    # ── Platform files ───────────────────────────────────────────────────────
    required_platforms = set(selected_platforms or []) | set(detect_required_platforms(scan.get("stack", {}) or {}))
    for platform in sorted(required_platforms):
        rel = PLATFORM_FILE_MAP.get(platform)
        if rel:
            write_file(repo / rel, platform_contents(platform, scan), force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)

    # ── Root agent instruction files (CLAUDE.md, AGENTS.md) ─────────────────
    for fname in ROOT_GENERATED_FILES:
        write_root_agent_file(repo / fname, repo_name, created=created, updated=updated, skipped=skipped)

    # ── Verification + repair loop (up to 3 passes) ──────────────────────────
    # Each pass forces-writes anything still missing. After 3 passes any
    # remaining gaps are a hard failure that the caller must report clearly.
    verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=required_platforms)
    for _repair_pass in range(3):
        if verification["status"] == "passed":
            break
        for d in verification.get("missing_required_directories", []):
            (repo / d).mkdir(parents=True, exist_ok=True)
        for f in verification.get("missing_required_files", []):
            sub = f.replace("project-atlas/", "")
            file_content = contents.get(sub, f"# {Path(sub).stem.replace('-', ' ').title()}\n\nGenerated placeholder. Update with confirmed project context.\n")
            write_file(repo / f, file_content, force=True, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
        for f in verification.get("missing_platform_files", []):
            platform = Path(f).stem
            write_file(repo / f, platform_contents(platform, scan), force=True, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
        for fname in verification.get("missing_root_files", []):
            write_root_agent_file(repo / fname, repo_name, created=created, updated=updated, skipped=skipped)
        verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=required_platforms)

    # ── Detailed log entry ───────────────────────────────────────────────────
    v = verification
    missing_summary = ""
    all_missing = (
        v.get("missing_required_files", []) +
        v.get("missing_required_directories", []) +
        v.get("missing_platform_files", []) +
        v.get("missing_root_files", [])
    )
    if all_missing:
        missing_summary = "\n- MISSING: " + ", ".join(all_missing)

    log_text = f"""
## {now_iso()} - Atlas generation

- Created: {len(created)}
- Updated: {len(updated)}
- Skipped existing: {len(skipped)}
- Backed up: {len(backed_up)}
- Verification status: {v['status']}{missing_summary}
"""
    append_log(repo / "project-atlas/maintenance-log.md", log_text)

    return {
        "status": v["status"],
        "created": [str(p.relative_to(repo)) for p in created if p.exists()],
        "updated": [str(p.relative_to(repo)) for p in updated if p.exists()],
        "skipped": [str(p.relative_to(repo)) for p in skipped if p.exists()],
        "backed_up": [str(p.relative_to(repo)) for p in backed_up if p.exists()],
        "verification": v,
    }

GREENFIELD_FILES = [
    "project-atlas/README.md", "project-atlas/agent-playbook.md", "project-atlas/.project-atlasignore",
    "project-atlas/plan/README.md", "project-atlas/plan/product-brief.md", "project-atlas/plan/stack-proposal.md", "project-atlas/plan/architecture-plan.md", "project-atlas/plan/data-model-plan.md", "project-atlas/plan/auth-plan.md", "project-atlas/plan/feature-plan.md", "project-atlas/plan/implementation-roadmap.md", "project-atlas/plan/open-questions.md",
    "project-atlas/context/project-overview.md", "project-atlas/context/stack.md", "project-atlas/context/architecture.md", "project-atlas/context/code-map.md", "project-atlas/context/feature-index.md", "project-atlas/context/database.md", "project-atlas/context/auth-and-access.md", "project-atlas/context/conventions.md", "project-atlas/context/dependency-map.md", "project-atlas/context/testing.md", "project-atlas/context/deployment.md", "project-atlas/context/known-risks.md", "project-atlas/context/glossary.md", "project-atlas/context/open-questions.md", "project-atlas/context/maintenance-log.md",
    "project-atlas/decisions/README.md", "project-atlas/handoffs/README.md", "project-atlas/snapshots/README.md",
]


def create_greenfield(repo: Path, force: bool = False, backup: bool = False) -> Dict[str, Any]:
    created: List[Path] = []
    skipped: List[Path] = []
    updated: List[Path] = []
    backed_up: List[Path] = []
    for d in ["project-atlas/platforms", "project-atlas/decisions", "project-atlas/handoffs", "project-atlas/snapshots"]:
        (repo / d).mkdir(parents=True, exist_ok=True)
    for rel in GREENFIELD_FILES:
        title = Path(rel).stem.replace("-", " ").title()
        content = f"# {title}\n\nGreenfield Project Atlas placeholder. Replace with confirmed project details. Do not invent implementation facts.\n"
        if rel.endswith(".project-atlasignore"):
            content = ".git/\nnode_modules/\nvendor/\n.env\n.env.*\n*.pem\n*.key\n"
        write_file(repo / rel, content, force=force, backup=backup, created=created, skipped=skipped, updated=updated, backed_up=backed_up)
    # Root agent instruction files
    repo_name = repo.name
    root_created: List[Path] = []
    root_updated: List[Path] = []
    root_skipped: List[Path] = []
    for fname in ROOT_GENERATED_FILES:
        write_root_agent_file(repo / fname, repo_name, created=root_created, updated=root_updated, skipped=root_skipped)

    return {
        "status": "passed",
        "created": [str(p.relative_to(repo)) for p in created + root_created],
        "updated": [str(p.relative_to(repo)) for p in updated + root_updated],
        "skipped": [str(p.relative_to(repo)) for p in skipped + root_skipped],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Project Atlas template files.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--template-mode", choices=["existing", "greenfield"], default="existing")
    parser.add_argument("--scan-json")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--platform", action="append", default=[])
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if args.template_mode == "greenfield":
        result = create_greenfield(repo, force=args.force, backup=args.backup)
    else:
        if args.scan_json:
            scan = json.loads(Path(args.scan_json).read_text(encoding="utf-8"))
        else:
            scan = scan_repository(repo)
        result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform)

    print(dump_json(result))
    return 0 if result.get("status") == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
