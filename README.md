# Hermes — Governed Multi-Worker AI Coordinator (Windows)

Hermes Brain plans and verifies; allowlisted worker CLIs (Codex, Antigravity,
OpenCode) implement. One launcher owns every worker spawn: closed stdin, no
PTY, explicit whole-process timeout, per-task attempt budget, model/effort
allowlist, and one JSONL usage receipt per job. No retries by the launcher
itself, no provider failover, no invented model IDs.

## 60-second quickstart (Windows, Python 3.11+, stdlib only — no pip install)

```powershell
python --version                                  # 3.11+
python bin/test_hermes_routing.py                 # routing/launcher gates, seconds
python bin/test_hermes_stubgen.py                 # stub extractor (outer-ring pilot)
python bin/test_hermes_secretscan.py              # pre-publication secret scanner
python bin/hermes-worker.py --route codex-normal --task "synthetic dry run" `
  --workdir D:/Hermes/synthetic_demo --timeout 180 --dry-run
```

The dry run validates route, model/effort allowlist, workdir scope, timeout
policy, and argv construction without spawning any model. Real dispatch is
documented in `skills/autonomous-ai-agents/hermes-routing/SKILL.md`.

## Worker prerequisites (per route, only what you use)

| Route family | CLI | Auth |
|---|---|---|
| `codex-*` | Codex CLI | Two accounts: Brain store vs dedicated worker home (never copy between them) |
| `antigravity-*` | Antigravity CLI (`agy`) | `agy` login |
| `opencode-*` | OpenCode | Bedrock credentials for paid routes; contributor route is synthetic/public only |

## Repo layout

| Path | What |
|---|---|
| `bin/hermes-worker.py` | The only invocation boundary (enforces everything) |
| `worker-catalog.json` | Single source of truth: routes, models, efforts, budgets, timeouts |
| `skills/autonomous-ai-agents/hermes-routing/SKILL.md` | Routing procedure, tiers, fixup/resume protocol |
| `bin/hermes-stubgen.py` | Redacted stub extractor (outer-ring pilot, Python only) |
| `bin/hermes-secretscan.py` | Secret scanner: exit 2 on findings in publishable files |
| `synthetic_demo/` | Safe sandbox for dry runs and contributor tasks |
| `AGENTS.md`, `SOUL.md` | Coordinator operating contract |

## Vendor boundary (how upstream updates merge)

This repo tracks only the coordination layer. The vendor product underneath
(`hermes.exe`, `hermes-agent/`, bundled skills, auth stores, logs) is never
committed — see `.gitignore`. When Hermes ships an update: install it in
place, then run the re-probe procedure in
`skills/autonomous-ai-agents/hermes-routing/SKILL.md` (read-only, no
inference). If a CLI changed flags or models, update the route entry plus a
deterministic test; small edits accepted, the gates enforce the rest. Sandbox
hygiene: never `git init` inside `synthetic_demo/` (a nested repo breaks
`git add` for the whole sandbox); the root repo already satisfies the
worktree check. Never commit `auth.json`, `.codex_worker/`, `logs/`,
`backups/`, or `tasks/` — `python bin/hermes-secretscan.py` gates every push
via CI.

## Secrets

Never commit `auth.json`, `.codex_worker/`, `logs/`, `backups/`, or `tasks/`
— `.gitignore` already excludes them. Before any public push, run
`python bin/hermes-secretscan.py` (exit 0 required) and re-check
`allowed_workdir_roots` in `worker-catalog.json` for your machine.

## License

MIT — see `LICENSE`.
