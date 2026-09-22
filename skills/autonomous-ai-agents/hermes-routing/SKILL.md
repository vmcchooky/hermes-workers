---
name: hermes-routing
description: "Route Hermes work to an allowlisted worker."
version: 0.8.1
author: Hermes Supervisor, Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [Hermes, Routing, Workers, Usage]
    related_skills: [codex, opencode, antigravity-cli]
---

# Hermes Routing Skill

Use the single root catalog `worker-catalog.json` as the source of truth for
worker model IDs, reasoning settings, scopes, and usage sources. This skill
does not perform inference itself and does not replace a worker's result with
a second implementation. The launcher (`bin/hermes-worker.py`) enforces the
model/effort allowlist in code; this text never authorizes a pair the code rejects.

## When to Use

- Coding, refactoring, or implementation work that Hermes Brain should delegate.
- Independent review or hard analysis that needs a named worker route.
- A route/configuration dry-run or a usage-receipt check.

Do not use the contributor route for private source, captured configs, or
credentials. Do not use a second worker only to run a test or build.

## Prerequisites

- The requested route exists and is `available` in `worker-catalog.json`.
- The selected workdir satisfies the route scope.
- The relevant CLI login/configuration already exists; never copy auth between CLIs.
- Brain auth is Hermes-owned (`D:/Hermes/auth.json`); Codex workers use the
  dedicated `D:/Hermes/.codex_worker/auth.json`. A Codex desktop login does not
  update Brain. If Brain must use another account, run the official
  `hermes auth add openai-codex` flow and choose the account yourself; never
  synchronize or auto-rotate the two stores.
- Use the `terminal` tool with the launcher below. The launcher closes stdin and
  runs without a PTY.

## How to Run

```text
terminal(command="D:/Hermes/hermes-agent/venv/Scripts/python.exe D:/Hermes/bin/hermes-worker.py --route <route> --task-file <task-file> --workdir <exact-workdir> --timeout 600", pty=false, background=true, notify=true)
```

`--timeout` is a hard wall for the whole child worker process (local commands,
builds, tests included), never per-turn. Tiered deadlines: draft/small fix
`--timeout 180`; hard logic `--timeout 300`; standard `--timeout 600`. Total
spawned walls per key cap 1200s. Above 600, above the 1200 total, or a 3rd
attempt after 2 timeouts needs `--timeout-approval <note>` (only its hash is
recorded) — and the 3rd attempt must also change route or shrink scope, never
an identical full-scope rerun. Split large work at a checkpoint first (one
worker call = one phase); never extend the deadline implicitly; never retry a
timed-out task without reconciliation.

Resume (same tool only; cross-tool refused): `--resume-session
<worker_session_id> --resume-from-job <prior-job_id>`. Same-key resumes
auto-verify against the ledger. A fixup after Brain's direct tests fail is a
NEW task-key (`--attempt-kind initial`, fresh budget) plus `--fixup-of
<origin> --fixup-depth <1|2>` in order (launcher enforces
`fixup_budget_exhausted`; 3rd failure → checkpoint + blocker).
Draft fixups 180s, hard-task fixups 300s. Resuming a timed-out session needs
prior reconcile plus `--reconciled`:

```text
terminal(command=".../hermes-worker.py --route <same-route> --task-file <fixup-task-file> --workdir <exact-workdir> --timeout 180 --resume-session <worker_session_id> --resume-from-job <prior-job_id> --fixup-of <origin-task-key> --fixup-depth <1-or-2>", ...)
```

Retries/fallbacks (the launcher never retries by itself — declare explicitly,
at most 1 same-route retry + 1 fallback, only for `provider_retryable`):

```text
terminal(command=".../hermes-worker.py --route <route> --task-file <task-file> --workdir <exact-workdir> --timeout 600 --attempt-kind retry --task-key <key>", ...)
terminal(command=".../hermes-worker.py --route <next-route> --task-file <task-file> --workdir <exact-workdir> --timeout 600 --attempt-kind fallback --fallback-from <route> --task-key <key>", ...)
```

Never reset the ledger or change the key to bypass budgets. Declare
`--data-class private` for non-synthetic tasks (refused on
synthetic-public-only routes). Dry-run checks configuration only — never
E2E/TUI/behavior. Config-only check:

```text
terminal(command="python bin/hermes-worker.py --route <route> --task \"synthetic dry run\" --workdir <workdir> --dry-run", timeout=30)
```

## Procedure

1. Read only the selected route entry and match difficulty, risk, data class,
   tool capability, quota, billing. Tests/builds run directly (no worker).
   Tiers: Tier-1 draft (`antigravity-normal` Flash/high or `codex-normal`
   Luna/max, 180s); Tier-2 hard (`codex-hard`/`codex-terra` Sol/Terra or
   `antigravity-hard` Pro, 300s) after Tier-1 stalls; Tier-3 review/paid
   (`codex-review` Astra/low, `antigravity-review` Opus integrated,
   `opencode-bedrock` Opus, 300s). Exceptions: crisp spec + pre-written tests
   → Tier-2 Sol directly; torn between tiers → higher one; trivial <2min work
   stays with Brain (26k+ fixed overhead per call). Synthetic order: Flash,
   contributor (6/6 ok), MiMo third (fastest/cheapest on 1 job; re-rank on
   next 5 verdicts only). `codex-normal` opens Tier-1 on probation for code
   tasks: log verdicts; if its code-task FPVR trails Tier-2 over the next 10
   verdicts, move code tasks to Flash/Sol. Never open with the heaviest model
   for UNCERTAIN work (the Sol-direct exception above is the only carve-out).
   Never private source to free tiers. Cost model
   (`scarce_resource`): Codex/Antigravity burn wall + rate-limit (optimize
   wall + first-pass rate); only Bedrock burns USD. Size tasks to tiers
   (~2500 chars; launcher warns >2500, refuses >6000 without
   `--size-approval`; no silent chunking across keys; monoliths banned).
   Explainable policies, not IQ rankings.
2. Delegate via the launcher (route/task/exact workdir; no invented flags).
   Resume as above (verified argv per tool; `receipt.resume` + ledger; no
   budget bypass; Codex resume needs the authorized full-access bypass). The
   launcher injects role lock + contract — never repeat them in task text.
   Single worktree writer, always.
3. At most one allowlisted `--reasoning-override` for adapter mismatches;
   never switch provider or loop. Test/review failures are task failures,
   never provider errors. `usage_limit_reached` + reset marker →
   `quota_exhausted_checkpoint` (no short retry, no same-bucket fallback, no
   credential rotation); transient 429 stays `provider_retryable`. Keep the
   background session; await notification; no repolling; never wrap the
   deadline in a shorter foreground timeout (progress diagnostics show
   in-flight work).
4. Inspect the result + `HERMES_WORKER_RECEIPT` (route/model/effort,
   `failure_class`, requested vs observed, `resume.mode`, timeout `tier`);
   one record also lands in `logs/worker_usage.jsonl`.
5. Run tests/builds/deterministic checks directly in the workdir; report
   separately from the worker status.
6. Report requested/observed model+reasoning, sessions, time, exit, test
   status, usage (`null` = unknown, not zero). Fallback failure → checkpoint
   + blocker, no loop.

## Task authoring checklist (first-pass rate is the cheapest token saver)

Task files state: (1) checkable done-criteria, (2) explicit out-of-scope,
(3) exact verify command, (4) concrete FIRST ACTION. Same-key retries reuse
byte-identical text (cache affinity).

## Fixup task template (standardized hand-off, no auto-loop)

Brain diagnoses first (test wrong? code wrong? environment wrong?) and only
then opens a fixup. Copy this template verbatim into the fixup task file:

```text
Fixup <depth>/2 of <origin-task-key> (prior job <job_id>, session <worker_session_id>).
Failing test: <test_name> — Brain ran: <exact command> in <workdir>.
Traceback (verbatim, trimmed to relevant frames):
<traceback>
Diff summary since the prior job: <files + hunks>.
Instruction: fix ONLY the failing path above. Do not refactor unrelated code.
Do not modify the test itself. Keep the diff minimal.
```

No auto-pipeline by design (`receipt.fixup` + ledger linkage, cap enforced).
Environment failures (missing dep, bad config) go to Brain directly, never
auto-resumed. Capability failures (wrong code, test diff) resume the session;
BEHAVIORAL failures (off-task, meta-dispatch, ignoring workdir) use a FRESH
session with explicit role instruction — resume replays confusion (proven live).

## Worktrees, fan-out, stubs, verdicts, re-probe

- Worktrees (Brain-created only; launcher never creates): confirm git repo
  (never under non-repo `D:\Hermes`), pre-register the allowlist path,
  `worktree add -b job-<id>`, dispatch, test directly, merge on PASS /
  remove + delete-branch on FAIL. Contributor route forbidden; parallel work
  needs distinct worktrees.
- Fan-out (micro proven: 2 Flash jobs, ~15s, JSONL intact): ALL conditions —
   disjoint writes, payload well above the measured 26–38k tokens fixed
   overhead per call (heuristic: no fan-out when the task payload is under
   ~8000 chars), no key
  on 3rd attempt (turn-3 goes sequential top tier). Diff/summary handoffs
  only; fail-fast downstream; 50k+ spikes need separate accounts (unproven).
- Stubs (`hermes-stubgen.py`, Python only): Brain reviews output (no bodies;
  defaults/decorators line-by-line; endpoints; regenerate per use) →
  `synthetic_demo` only; no Cline until a leak-free pilot.
- Verdicts/proxies (no USD inference, never cross-provider totals): FPVR via
  `logs/brain_verdicts.jsonl` append (`python -c "import json;open(
  'logs/brain_verdicts.jsonl','a').write(json.dumps({'job_id':'<id>',
  'route':'<route>','test_status':'pass|fail',
  'origin':'<session-or-operator>'})+'\n')"`); tag origin for stratification
  and recompute FPVR with/without foreign origins before citing trends
  (reporter dedupes by job_id, keeps last); churn on git repos only;
  tool-density within one task family only; compare non-cached medians
  within one tool for resume economics (resumed threads inherit cache bulk,
  so raw medians mislead).
- Re-probe quarterly or after CLI updates (read-only, no inference):
  `codex exec --help`, `agy --help`, `agy models`. On change, update the
  route entry plus a deterministic test.

## Deferred items register (reviewed quarterly with the re-probe)

| Item | Revisit trigger |
|---|---|
| Jev classifier integration | user-supplied API key + 10-task shadow pilot measuring FPVR delta |
| Dynamic model selector | N≥200 labeled verdicts |
| Streaming stdout reader | STAYS CUT unless new adapter evidence (single-JSON adapters gain zero) |
| Job Object cleanup | launcher-crash orphan evidence in production |
| Language port | profile proving launcher overhead matters (now 168ms vs 15–600s jobs) |
| Ledger index/DB | N≥100k receipts |
| Task-key budget race | CLOSED by per-key lock (fail-closed `taskkey_busy`) + single-coordinator discipline |

## Model/effort allowlist (enforced by the launcher)

- Codex: Luna = max only; Terra/Sol = low/medium/high/xhigh (never
  max/ultra); Astra = low only. Availability = per-route `available` flag;
  never invent IDs.
- Antigravity: Flash/Pro use `--effort high`; Opus Thinking uses integrated
  reasoning with the exact label `model-integrated/default, effort chưa xác
  nhận`; if Opus is unavailable, route Pro instead.
- OpenCode: Contributor = xhigh, synthetic/public only, never private
  source/creds; Bedrock = high or max, paid fallback, bounded invocations.
- Brain: Sol/high default, Luna/max fallback only. Never apply the worker
  fallback chain to Brain implicitly.

## Pitfalls

- Worker errors never authorize provider failover (Brain fallback is separate
  in `config.yaml`). Token semantics differ per adapter (Codex inclusive vs
  raw); cost = terminal events only; CanonicalUsage keeps input uncached;
  never cross-provider totals. Cost fields stay adapter telemetry, not a bill.
- agy zero-exit with denied_actions/empty response = blocked. Full-access is
  authorized; this is not an OS sandbox. Unknown stays unknown (no USD,
  quota, or model inference); dry-run proves invocation only, never behavior.
- Adapter rejections are configuration failures: keep history, fix the route.
  No early kill (456s precedent) and no streaming reader (evaluated + CUT);
   diagnose via `progress_snapshot`. Tree-kill (`taskkill /T /F` with
   ownership check) exists; Job Object stays deferred to the launcher-crash
   case.
- Stubs go stale → regenerate per use. `prompt_est_tokens` is a rough
   estimate, not measured usage; killed-turn output blindness is adapter-side
   (Codex input recoverable post-hoc from the session store
   (`thread_token_usage`), counts only, never text).
- Role lock goes first and is injected by the launcher — never duplicate it
  in task text. Contamination (`AGENTS.md` auto-load) is neutralized via
  prompt + `synthetic_demo/AGENTS.override.md`; session files stay local
  (no credential values ever found in stores).
- Jev classifier deferred (needs key + pilot; regex classifier stays).
- Per-call overhead decomposes to ~1k chars launcher header + ~2.7k AGENTS.md
  auto-load + task text; the remaining ~20k+ tokens are provider-side system
  context, unobservable and untrimmable from here — trim task text, not the
  header.
- Single coordinator REQUIRED, not assumed: a second operator was observed
  live, and concurrent launches break budget/ledger atomicity assumptions.
  The per-key lock turns concurrent launches into fail-closed refusals, but
  by policy never run two coordinators against the same task-keys; designate
  one writer, others read receipts only.
- `D:\Hermes` is not a repo: no worktrees, no churn metric there.

## Verification

```text
terminal(command="python bin/test_hermes_routing.py", timeout=60)
terminal(command="python bin/test_hermes_stubgen.py", timeout=60)
terminal(command="python bin/test_hermes_secretscan.py", timeout=60)
terminal(command="python bin/test_hermes_usage_report.py", timeout=60)
terminal(command="python bin/hermes-usage-report.py", timeout=60)
terminal(command="bin/hermes.exe config check", timeout=60)
terminal(command="D:/Hermes/hermes-agent/venv/Scripts/python.exe D:/Hermes/bin/hermes-worker.py --route codex-normal --task \"synthetic dry run\" --workdir D:/Hermes/synthetic_demo --timeout 180 --dry-run", timeout=30)
terminal(command="D:/Hermes/hermes-agent/venv/Scripts/python.exe D:/Hermes/bin/hermes-worker.py --route antigravity-normal --task \"synthetic resume dry run\" --workdir D:/Hermes/synthetic_demo --timeout 180 --resume-session 378f5d8e-698d-407b-b1a9-9861df2bd5e9 --dry-run", timeout=30)
```

These checks must not call a worker model. The official end-to-end test is a
separate follow-up and must use a synthetic/public task before any private
repository work is routed.
