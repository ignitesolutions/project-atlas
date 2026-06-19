# 🗺️ Project Atlas

**AI-readable project context for software repositories.**

Project Atlas generates and maintains a `project-atlas/` folder in your repo — a structured set of markdown files that give any AI agent (Claude Code, ChatGPT, Cursor, etc.) the context it needs to work effectively without re-reading your entire codebase on every session.

---

## What it does

When you run Project Atlas on a repository, it scans your codebase and generates a set of concise, structured documentation files covering:

- Project purpose and overview
- Tech stack and dependencies
- Architecture and code map
- Database schema and access patterns
- Auth and access control
- Deployment and infrastructure
- Known risks and fragile areas
- Feature index and conventions

It also generates `CLAUDE.md` and `AGENTS.md` at your repository root, which tell AI agents to read the playbook and keep Atlas updated after every task.

---

## How it works

Project Atlas is an AI skill — a `SKILL.md` file that instructs a compatible AI agent how to scan a repo, generate the Atlas documentation, and maintain it over time. The skill ships with:

- **`SKILL.md`** — the master instruction set read by the AI
- **`scripts/`** — optional Python scripts for deterministic local execution
- **`templates/`** — file templates for existing codebases and greenfield projects
- **`references/`** — detailed schemas, workflows, and platform guides the AI loads on demand
- **`agents/`** — per-platform agent configuration (`openai.yaml`, `claude-code.md`)

---

## Compatibility

| Platform | Support |
|---|---|
| Claude Code | ✅ Native (reads `SKILL.md` directly) |
| ChatGPT Custom GPT | ✅ Via `agents/openai.yaml` and Code Interpreter |
| Claude.ai | ✅ Upload skill and repo context |
| Cursor / Windsurf / other agents | ✅ Read `SKILL.md` as context |
| Local / CLI | ✅ Run `scripts/bootstrap_atlas.py` directly |

---

## Quickstart

### With Claude Code

1. Download `project-atlas.zip` from [Releases](../../releases)
2. In Claude Code, open your repo and say:

   > "Bootstrap this repository using the Project Atlas skill"

   Attach or reference the skill zip. Claude Code will scan the repo, generate all Atlas files, and create `CLAUDE.md` and `AGENTS.md` at the repo root.

### With ChatGPT

1. Upload `project-atlas.zip` to a ChatGPT session with Code Interpreter enabled
2. Say:

   > "Bootstrap this repository using the Project Atlas skill"

   Upload or reference your repo files. ChatGPT will run the scripts and generate the Atlas output.

### Local / CLI

Unzip the skill to a working directory and run:

```bash
# Bootstrap an existing codebase
python project-atlas/scripts/bootstrap_atlas.py --repo /path/to/repo --mode existing

# Set up a greenfield project
python project-atlas/scripts/bootstrap_atlas.py --repo /path/to/repo --mode greenfield

# Check for missing or outdated Atlas files
python project-atlas/scripts/maintain_atlas.py --repo /path/to/repo --mode check

# Update Atlas after code changes
python project-atlas/scripts/maintain_atlas.py --repo /path/to/repo --mode update
```

> **Note:** The `scripts/` folder is a companion tool for local use. It is never copied into the generated repository output.

---

## Generated output

After bootstrapping, your repo will contain:

```
your-repo/
├── CLAUDE.md                          ← tells Claude Code to read the playbook
├── AGENTS.md                          ← tells OpenAI agents to read the playbook
└── project-atlas/
    ├── README.md
    ├── agent-playbook.md              ← before/after rules for every AI session
    ├── project-overview.md
    ├── stack.md
    ├── architecture.md
    ├── code-map.md
    ├── feature-index.md
    ├── database.md
    ├── auth-and-access.md
    ├── conventions.md
    ├── dependency-map.md
    ├── testing.md
    ├── deployment.md
    ├── known-risks.md
    ├── glossary.md
    ├── open-questions.md
    ├── maintenance-log.md
    ├── .project-atlasignore
    ├── platforms/                     ← per-platform detail (cfml, docker, etc.)
    ├── decisions/                     ← architecture decision records
    ├── handoffs/                      ← session handoff notes
    └── snapshots/                     ← point-in-time Atlas snapshots
```

---

## The agent playbook

The most important generated file is `project-atlas/agent-playbook.md`. Every AI agent session should start by reading it. It tells the agent:

**Before every task** — which Atlas files to read, what risks to check, and where to find relevant code.

**After every task** — which Atlas file to update based on what changed:

| What changed | Update this file |
|---|---|
| Features added, moved, or removed | `feature-index.md` |
| Routes, services, or components | `code-map.md` |
| Auth, sessions, or permissions | `auth-and-access.md` |
| Schema, migrations, or queries | `database.md` |
| Runtimes, frameworks, dependencies | `stack.md` + `dependency-map.md` |
| Build, deploy, hosting, or CI | `deployment.md` |
| Fragile or security-sensitive areas | `known-risks.md` |
| Coding conventions or patterns | `conventions.md` |

`CLAUDE.md` and `AGENTS.md` repeat this directive at the repo root so it is enforced even if an agent doesn't read deep into `project-atlas/`.

---

## Keeping Atlas up to date

Atlas is designed to stay current. `CLAUDE.md` and `AGENTS.md` instruct every AI agent to review and update the relevant files after completing any task that durably changes the codebase.

For manual updates or repairs:

```bash
# See exactly what's missing
python project-atlas/scripts/maintain_atlas.py --repo . --mode check

# Repair missing files and update changed ones
python project-atlas/scripts/maintain_atlas.py --repo . --mode update

# Force-regenerate a specific file (e.g. after deleting it)
rm project-atlas/agent-playbook.md
python project-atlas/scripts/maintain_atlas.py --repo . --mode update
```

---

## Options

| Flag | Description |
|---|---|
| `--mode existing` | Bootstrap an existing codebase |
| `--mode greenfield` | Set up a new project |
| `--mode check` | Verify all required files exist |
| `--mode update` | Repair missing files and update changed ones |
| `--force` | Overwrite existing Atlas files |
| `--backup` | Save `.bak` copies before overwriting (use with `--force`) |
| `--platform <name>` | Force a platform to be included (e.g. `cfml`, `docker`) |

---

## Requirements

Python 3.9+ (for local script use). No external dependencies — stdlib only.

---

## License

Apache 2.0
