# Hermes Brain Coordination

Hermes Brain is the coordinator. The worker route source of truth is
`worker-catalog.json`; the invocation boundary is
`bin/hermes-worker.py`; the routing procedure is
`skills/autonomous-ai-agents/hermes-routing/SKILL.md`.

## Required behavior

- Brain is configured as `openai-codex/gpt-6-sol` with `high` reasoning.
- Brain's only configured fallback is `openai-codex/gpt-6-luna` with `max`;
  report explicitly whenever that fallback is used.
- Delegate implementation, difficult analysis, and review to an allowlisted
  worker route. Do not redo the worker's coding task in Brain.
- Run tests, builds, and deterministic checks directly in the target workdir;
  do not start a second worker only to run them.
- Use the launcher with closed stdin and no PTY. Keep the route, model, and
  reasoning explicit in the invocation.
- Launch workers with terminal background=true, notify=true, pty=false and a
  tiered launcher timeout (draft/small fix: --timeout 180; hard logic: --timeout
  300; standard default: --timeout 600; above 600 only with --timeout-approval).
  Retain the process session and await notification;
  never cut off a worker with a shorter foreground terminal timeout.
- Do not switch provider after a worker failure or quota error. Allow at most
  one catalog-declared reasoning invocation correction, then report the route
  as blocked.
- Read the worker receipt and `logs/worker_usage.jsonl`. Keep Brain usage and
  worker usage separate; missing token fields are unknown, not zero.

## Scope and safety

- Supervisor authorized non-interactive full-access worker execution on
  2026-09-19. Launcher applies process-local permission overrides to all three
  CLIs; this does not grant Windows Administrator privileges. Workdir allowlists
  select starting directories, NOT a filesystem sandbox. Keep task scope and
  contributor data restrictions below; do not claim OS isolation.

- Workdirs are limited by the catalog. This installation is for `D:\Hermes`,
  with one Supervisor-approved exception for non-Contributor routes:
  `D:\Quorix\moonstorm\scratch\g2-integration`. That exception is limited to
  the MoonStorm G2 integration task and does not authorize other MoonStorm
  worktrees or broader `D:\` access.
- The OpenCode contributor route is synthetic/public-only. Never send private
  source, MoonStorm source/diffs/logs, captured device configs, credentials, or
  tokens through it.
- Preserve each changed file's timestamped backup under `backups/` before an
  edit. Do not modify vendor core unless an independent blocker is reported.
