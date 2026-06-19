#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
from pathlib import Path

try:
    from scan_repo import scan_repository
    from write_templates import create_existing
    from utils import append_log, dump_json, now_iso, verify_existing_atlas
except ImportError:
    from .scan_repo import scan_repository
    from .write_templates import create_existing
    from .utils import append_log, dump_json, now_iso, verify_existing_atlas


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain or verify Project Atlas.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--mode", choices=["check", "update"], default="check")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--platform", action="append", default=[])
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    scan = scan_repository(repo)

    if args.mode == "update":
        result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform)
        result["mode"] = "update"
    else:
        verification = verify_existing_atlas(repo, stack=scan.get("stack", {}), scan=scan, selected_platforms=args.platform)
        v = verification
        all_missing = (
            v.get("missing_required_files", []) +
            v.get("missing_required_directories", []) +
            v.get("missing_platform_files", []) +
            v.get("missing_root_files", [])
        )
        missing_line = ("\n- MISSING: " + ", ".join(all_missing)) if all_missing else ""
        append_log(
            repo / "project-atlas/maintenance-log.md",
            f"\n## {now_iso()} - Atlas check\n\n- Verification status: {v['status']}{missing_line}\n"
        )
        result = {"status": v["status"], "mode": "check", "verification": v}

    print(dump_json(result))
    if result.get("status") != "passed":
        v = result.get("verification", {})
        all_missing = (
            v.get("missing_required_files", []) +
            v.get("missing_required_directories", []) +
            v.get("missing_platform_files", []) +
            v.get("missing_root_files", [])
        )
        print("\nProject Atlas verification FAILED. Missing:")
        for m in all_missing:
            print(f"  - {m}")
        if not all_missing:
            print("  (see verification output above for details)")
        print("\nRun with --mode update to repair missing files.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
