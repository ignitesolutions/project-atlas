#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
import json
import subprocess
from pathlib import Path

try:
    from scan_repo import scan_repository
    from write_templates import create_existing, create_greenfield, convert_greenfield
    from utils import append_log, dump_json, now_iso, verify_existing_atlas, load_manifest, migrate_manifest, atomic_write_text, repository_fingerprint, atlas_lock, SKILL_VERSION
except ImportError:
    from .scan_repo import scan_repository
    from .write_templates import create_existing, create_greenfield, convert_greenfield
    from .utils import append_log, dump_json, now_iso, verify_existing_atlas, load_manifest, migrate_manifest, atomic_write_text, repository_fingerprint, atlas_lock, SKILL_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain or verify Project Atlas.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--mode", choices=["check", "update", "reconcile", "convert", "migrate"], default="check")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--platform", action="append", default=[])
    parser.add_argument("--level", choices=["structure", "evidence", "semantic"], default="semantic")
    parser.add_argument("--changed-since", help="Limit update domains to paths changed since this Git ref")
    parser.add_argument("--paths", action="append", default=[], help="Changed path to classify; repeat as needed")
    parser.add_argument("--domain", action="append", choices=["all", "code", "architecture", "database", "auth", "deployment", "operations"], default=[])
    parser.add_argument("--max-files", type=int, default=20000)
    parser.add_argument("--allow-partial-scan", action="store_true")
    parser.add_argument("--generation-mode", choices=["auto", "existing", "greenfield"], default="auto")
    parser.add_argument("--log", action="store_true", help="In check mode, also append the result to maintenance-log.md")
    parser.add_argument("--site-url", default="", help="Public-facing site URL to record in agent-playbook.md (update/reconcile/convert modes). If omitted, whatever is already recorded is preserved.")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    changed_paths = list(args.paths)
    if args.changed_since:
        result = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", args.changed_since, "--"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(json.dumps({"status": "failed", "diagnostics": [{"code": "INVALID_GIT_REF", "paths": [args.changed_since], "message": result.stderr.strip(), "suggested_repair": "Use a valid Git revision."}]}, indent=2))
            return 1
        changed_paths.extend(p for p in result.stdout.splitlines() if p)

    scan = scan_repository(repo, max_files=args.max_files, write_cache=args.mode in {"update", "convert"}, restrict_paths=changed_paths)
    if scan.get("truncated") and not args.allow_partial_scan:
        result = {"status": "failed", "mode": args.mode, "generation_mode": args.generation_mode, "lifecycle_state": "stale", "created": [], "updated": [], "diagnostics": [{"code": "PARTIAL_SCAN", "paths": [scan.get("truncated_at")], "message": "Repository scan was truncated.", "suggested_repair": "Increase --max-files or pass --allow-partial-scan."}], "verification": None}
        print(dump_json(result))
        return 1

    domains = set(args.domain)
    for path in changed_paths:
        low = path.lower()
        if any(token in low for token in ["auth", "login", "session", "permission", "role"]): domains.add("auth")
        elif any(token in low for token in ["sql", "schema", "migration", "database", "repository", "dao"]): domains.add("database")
        elif any(token in low for token in ["deploy", "docker", "workflow", "jenkins", "config"]): domains.add("deployment")
        else: domains.add("code")

    if args.mode == "migrate":
        raw, error = load_manifest(repo)
        if error:
            result = {"status": "failed", "mode": "migrate", "generation_mode": args.generation_mode, "lifecycle_state": "stale", "created": [], "updated": [], "diagnostics": [{"code": "MANIFEST_INVALID_JSON", "paths": ["project-atlas/atlas.json"], "message": error, "suggested_repair": "Repair the manifest before migration."}], "verification": None}
        else:
            migrated = migrate_manifest(raw, repo)
            current_fingerprints = {p: v for p, v in (scan.get("file_fingerprints", {}) or {}).items() if not p.startswith("project-atlas/") and p not in {"AGENTS.md", "CLAUDE.md"}}
            migrated["file_fingerprints"] = current_fingerprints
            migrated["repository_fingerprint"] = repository_fingerprint(f"{p}:{value}" for p, value in current_fingerprints.items())
            atomic_write_text(repo / "project-atlas/atlas.json", json.dumps(migrated, indent=2, sort_keys=True) + "\n")
            verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform, level="structure", generation_mode=args.generation_mode)
            result = {"status": verification["status"], "mode": "migrate", "generation_mode": verification["generation_mode"], "lifecycle_state": verification["lifecycle_state"], "created": [], "updated": ["project-atlas/atlas.json"], "diagnostics": verification["diagnostics"], "verification": verification}
    elif args.mode == "convert":
        result = convert_greenfield(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform, site_url=args.site_url)
        result["mode"] = "convert"
    elif args.mode in ("update", "reconcile"):
        manifest_path = repo / "project-atlas/atlas.json"
        old_manifest = {}
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
        except json.JSONDecodeError:
            pass
        current_fingerprints = {p: v for p, v in (scan.get("file_fingerprints", {}) or {}).items() if not p.startswith("project-atlas/") and p not in {"AGENTS.md", "CLAUDE.md"}}
        effective_mode = args.generation_mode if args.generation_mode != "auto" else old_manifest.get("generation_mode", "existing")
        skill_version_matches = old_manifest.get("skill_version") == SKILL_VERSION
        # `--mode reconcile` always takes the full regeneration path below, even when nothing in
        # the repo's source changed, since a skill upgrade doesn't touch repo fingerprints. It
        # never passes force=True on its own, so digest-tracked managed sections still refuse to
        # clobber hand-edited content — reconciliation only ever backfills what's missing or
        # unmodified since it last generated it.
        take_fast_path = (
            args.mode == "update" and skill_version_matches
            and old_manifest.get("file_fingerprints") == current_fingerprints
            and not changed_paths and not domains and not args.force and effective_mode == "existing"
        )
        if take_fast_path:
            live = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform, level="semantic", generation_mode="existing")
            structure_incomplete = any(item["code"] == "STRUCTURE_MISSING" for item in live["diagnostics"])
            if structure_incomplete:
                # Source files are unchanged, but required Atlas structure is missing (e.g. the
                # installed skill version added new required files since this repo was bootstrapped).
                # Repair through the normal write path: it only ever fills in missing files/dirs and
                # never overwrites hand-authored content.
                result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform, update=True, domains=domains, site_url=args.site_url)
            else:
                structural_codes = {"MANIFEST_INVALID_JSON", "MANIFEST_SCHEMA_UNSUPPORTED", "MANIFEST_FIELD_MISSING", "MANIFEST_FIELD_INVALID", "GENERATED_CONTENT_MODIFIED", "MANAGED_SENTINEL_INVALID"}
                hard_diagnostics = [item for item in live["diagnostics"] if item["code"] in structural_codes]
                updated_files = []
                if not hard_diagnostics and old_manifest.get("lifecycle_state") != live["lifecycle_state"]:
                    old_manifest["lifecycle_state"] = live["lifecycle_state"]
                    old_manifest["last_verified_state"] = live["lifecycle_state"]
                    old_manifest["generated_at"] = now_iso()
                    atomic_write_text(manifest_path, json.dumps(old_manifest, indent=2, sort_keys=True) + "\n")
                    updated_files.append("project-atlas/atlas.json")
                result = {"status": "failed" if hard_diagnostics else "passed", "mode": args.mode, "generation_mode": "existing", "lifecycle_state": live["lifecycle_state"], "created": [], "updated": updated_files, "skipped": [], "diagnostics": hard_diagnostics, "verification": live, "no_changes": not updated_files}
        elif effective_mode == "greenfield":
            result = create_greenfield(repo, force=args.force, backup=args.backup, site_url=args.site_url)
        else:
            result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform, update=True, domains=domains, site_url=args.site_url)
        result["mode"] = args.mode
    else:
        # Check mode is read-only: it must not touch the repository, so it can run
        # in CI or pre-commit without dirtying the tree. Pass --log to also record
        # the result in maintenance-log.md.
        verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform, level=args.level, generation_mode=args.generation_mode)
        v = verification
        if args.log:
            all_missing = (
                v.get("missing_required_files", []) +
                v.get("missing_required_directories", []) +
                v.get("missing_platform_files", []) +
                v.get("missing_root_files", [])
            )
            missing_line = ("\n- MISSING: " + ", ".join(all_missing)) if all_missing else ""
            with atlas_lock(repo):
                append_log(
                    repo / "project-atlas/maintenance-log.md",
                    f"\n## {now_iso()} - Atlas check\n\n- Verification status: {v['status']}{missing_line}\n"
                )
        result = {"status": v["status"], "mode": "check", "generation_mode": v["generation_mode"], "lifecycle_state": v["lifecycle_state"], "created": [], "updated": [], "diagnostics": v["diagnostics"], "verification": v}

    print(dump_json(result))
    if result.get("status") != "passed":
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
