#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import argparse
from pathlib import Path

try:
    from scan_repo import scan_repository
    from write_templates import create_existing, create_greenfield
    from utils import dump_json
except ImportError:
    from .scan_repo import scan_repository
    from .write_templates import create_existing, create_greenfield
    from .utils import dump_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Project Atlas for a repository.")
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--mode", choices=["existing", "greenfield"], default="existing")
    parser.add_argument("--force", action="store_true", help="Overwrite existing Atlas files")
    parser.add_argument("--backup", action="store_true", help="Back up overwritten files as .bak")
    parser.add_argument("--platform", action="append", default=[], help="Explicit platform file to create, e.g. cfml or mssql")
    parser.add_argument("--max-files", type=int, default=20000)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if args.mode == "greenfield":
        result = create_greenfield(repo, force=args.force, backup=args.backup)
    else:
        scan = scan_repository(repo, max_files=args.max_files)
        result = create_existing(repo, scan, force=args.force, backup=args.backup, selected_platforms=args.platform)
        result["scan_summary"] = {
            "file_count": scan.get("file_count"),
            "dir_count": scan.get("dir_count"),
            "stack": scan.get("stack"),
            "cfc_count": len(scan.get("cfc_inventory", []) or []),
        }

    print(dump_json(result))
    if result.get("status") != "passed":
        print("Project Atlas generation is incomplete. See verification details above.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
