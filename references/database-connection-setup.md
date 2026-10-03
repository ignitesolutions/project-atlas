# Database connection setup

This is a gate, not a suggestion: bootstrap does not proceed past it until either a connection is
successfully verified, or the user explicitly says to skip it. "I'll set it up later" is never a
valid resolution — if the user doesn't clearly say skip, keep working the section (ask again, ask
for corrected details, whatever is blocking) rather than moving on. Ask **one question at a time**
throughout — never bundle several pieces of information into a single ask.

1. **Confirm the engine.** Detected stack signals (e.g. `mongo`, `mssql`, `mysql`) are a
   hypothesis, not a fact.
   - If evidence was found, state plainly what it was and where (e.g. "found a MongoDB connection
     string in `config/db.js`"), then ask exactly one question: "I think you're using
     `{engine}`. Is this correct?"
     - Yes → go to step 2.
     - No → ask a separate follow-up: "What database are you using? (or say skip)" A named engine
       → go to step 2 with that engine. "Skip" → stop the entire database section for this run —
       no `database.md`/`schema.md` stubs, no connection setup.
   - If no evidence was found, ask one combined question since there's nothing to confirm or deny:
     "Does this project use a database? If so, which engine?" No database → stop, no stubs. Skip →
     stop entirely. Named engine → go to step 2.
   - Never silently treat a detected engine as confirmed, and never silently treat absent evidence
     as "no database." Only proceed once the user has given an explicit answer.
2. **Ask whether to set up a live connection now**, or skip.
   - If the user declines, ask explicitly for confirmation that this bootstrap run should proceed
     without a verified connection. Record that explicit skip in `database.md` (e.g. "connection
     setup skipped by user on `<date>`"). Only an explicit skip unblocks the gate — do not
     interpret silence, a topic change, or a vague "later" as a skip.
   - Yes → go to step 3.
3. **Resolve the CLI tool.** Map the confirmed engine to its standard CLI (extend by the same
   pattern — a native, non-interactive client with env-var auth where one exists — for engines not
   listed):

   | Engine | CLI |
   | --- | --- |
   | mssql / sql server | `sqlcmd` |
   | mysql / mariadb | `mysql` |
   | postgres / postgresql | `psql` |
   | mongodb / mongo | `mongosh` (fall back to `mongo` if `mongosh` is absent) |
   | oracle | `sqlplus` |
   | sqlite | `sqlite3` |
   | redis | `redis-cli` |

   Run `command -v <tool>`.
   - Found → go to step 4.
   - Not found → ask one question: "I can't find `<tool>` on PATH. Want to give me the full path
     to it, or fix your PATH yourself and have me retry?"
     - Path given → verify it's executable, use it for the rest of setup.
     - "Fix PATH, retry" → wait for the user to say they're ready, re-run `command -v`, and loop
       this step until resolved or the user explicitly skips (back to step 2's skip path). Do not
       silently give up and jump to skip on the first miss.
4. **Collect connection details one field at a time — never bundled.** Ask a profile name/slug
   first (e.g. the site or repo name), then ask whatever fields the resolved CLI actually needs,
   each as its own question, waiting for the answer before asking the next:
   - `sqlcmd` / `mysql` / `psql` / `sqlplus` (host-based clients): host → port → database name →
     username → password.
   - `mongosh` / `mongo`: ask for a connection URI as a single field (the native way these tools
     take input); if the user doesn't have one, fall back to host → port → database name →
     username → password asked the same way.
   - `sqlite3`: just the database file path — no host/port/credentials exist for this engine.
   - `redis-cli`: host → port → username (optional) → password (optional).
5. **Test the connection** with a trivial read (`SELECT 1` for SQL engines,
   `db.runCommand({ping:1})` for mongo, `PING` for redis, etc.), passing the password via the
   client's environment-variable auth when one exists (`SQLCMDPASSWORD` for sqlcmd, `MYSQL_PWD`
   for mysql, `PGPASSWORD` for psql) rather than a CLI flag, so it never lands in shell history or
   process listings. Where a CLI has no such env var (e.g. `sqlplus`, `mongosh` without a URI),
   still never echo the password in any output the agent produces.
   - On failure, report the specific error, write nothing, and ask one question: retry (restart
     step 4's field sequence) or skip explicitly (back to step 2's skip path). Do not fall through
     without one of those two answers.
6. **On success:**
   - Create `project-atlas/local/db/` if it doesn't exist.
   - Write `project-atlas/local/db/<profile>.env` (`chmod 600`) with that CLI's native connection
     variables (e.g. `SQLCMDSERVER`/`SQLCMDDBNAME`/`SQLCMDUSER`/`SQLCMDPASSWORD` for sqlcmd,
     `MYSQL_HOST`/`MYSQL_TCP_PORT`/`MYSQL_DATABASE`/`MYSQL_USER`/`MYSQL_PWD` for mysql,
     `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` for psql), or for CLIs with no env-var
     convention, the values needed to build its invocation.
   - Write `project-atlas/local/db/agent-<tool>` (`chmod 700`) — a small wrapper that sources the
     profile's `.env` and execs the real client, mirroring the house-wide
     `/etc/sql/agent-sqlcmd <profile> ...` convention.
   - Ensure the repo's `.gitignore` contains `project-atlas/local/`, and add the same line to
     `.project-atlasignore` so future scans skip it.
   - Update `database.md` with only the profile name and invocation command, e.g. "Connect via
     `project-atlas/local/db/agent-sqlcmd <profile> -Q \"...\"`" — never the host, user, or
     password. This section is hand-authored; do not let later maintenance passes regenerate it.
