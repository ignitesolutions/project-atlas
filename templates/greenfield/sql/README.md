# SQL Scripts

Store generated or hand-authored `.sql` files here (migrations, seed data, ad hoc queries) —
never loose at the `project-atlas/` root. Never record secret values (passwords, keys, tokens,
connection strings) — names, locations, and access patterns only.

## Execution ledger

Add a row when a `.sql` file is created; fill an environment cell with the run date once the
file has been executed there. A blank cell means not yet run.

| File | Purpose | Dev | Stage | Live |
| --- | --- | --- | --- | --- |
