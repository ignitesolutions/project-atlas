# Final Verification Checklist

Before reporting success, verify all of the following:

1. Every exact required file exists.
2. Every exact required directory exists.
3. Required platform files exist only for detected or explicitly selected platforms.
4. No alias file is counted as satisfying a required file.
5. No Skill-internal directories were copied into generated output.
6. No root-level repo-specific Atlas document remains as a generic scaffold or placeholder.
7. The only intentionally scaffold-like files are `decisions/README.md`, `handoffs/README.md`, `snapshots/README.md`, `.project-atlasignore`, and `maintenance-log.md`.
8. No unexpected platform files such as `platforms/auth.md`, `platforms/testing.md`, `platforms/storage.md`, or `platforms/postgres.md` exist unless explicitly requested.
9. If `.cfc` files exist, every `.cfc` is represented in `code-map.md` or `platforms/cfml.md`. `cfc-index.md` is optional and cannot be the only discoverable inventory unless linked from a required file.
10. `maintenance-log.md` records the run and verification result.

If any item fails, report Atlas generation as incomplete and list the exact failing paths.
