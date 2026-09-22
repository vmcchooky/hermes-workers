---
name: hermes-routing
description: "Route Hermes work to an allowlisted worker."
version: 0.7.0
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

`--timeout` is a hard wall for the whole child worker process, including
local command execution, builds, race tests, and final diff checks. It is not a
per-turn or provider-only timeout. Use tiered deadlines instead of always 600:
draft/small fix → `--timeout 180`; hard logic/refactor → `--timeout 300`;
standard default → `--timeout 600`. Smaller tiers fail fast instead of burning
a full 600s black box. A large controlled task that combines
implementation, end-to-end work, and race/final validation must be split at a
checkpoint before dispatch (one worker call = one phase, see Procedure step 1).
If splitting is not practical, use a separately
approved per-task timeout, for example `--timeout 1200 --timeout-approval
<approval-note-or-id>`; the launcher records only a hash of the approval note.
Never extend the standard deadline implicitly or retry a timed-out task without
reconciliation.

Resume a prior worker session instead of cold-starting when fixing up its
output (same tool only; the launcher refuses cross-tool resume on fallback).
Pass the `worker_session_id` from the prior receipt plus `--resume-from-job`
as an audit link:

```text
terminal(command=".../hermes-worker.py --route <same-route> --task-file <fixup-task-file> --workdir <exact-workdir> --timeout 180 --resume-session <worker_session_id> --resume-from-job <prior-job_id>", ...)
```

A fixup after Brain's direct tests fail is a NEW task-key with its own budget,
not a retry: use `--attempt-kind initial` (fresh budget) with the resume flags
above, plus fixup audit flags so consecutive fixups stay capped:

```text
terminal(command=".../hermes-worker.py --route <same-route> --task-file <fixup-task-file> --workdir <exact-workdir> --timeout 180 --resume-session <worker_session_id> --resume-from-job <prior-job_id> --fixup-of <origin-task-key> --fixup-depth <1-or-2>", ...)
```

Cap: at most **2 consecutive fixup task-keys per origin** (launcher enforces
`fixup_budget_exhausted` above the catalog cap). Depths must arrive as 1, 2
in order under ONE stable `--fixup-of` identifier per chain (the launcher
counts recorded fixups across keys and refuses a depth that does not follow,
so depth-1-forever evasion fails). The third failure means save
a checkpoint and report a blocker. 180s fits draft-tier fixups; hard-task
fixups observed at 177–554s must use tier-2 300s. Resuming a timed-out session additionally requires prior reconcile plus
`--reconciled`.

Retries/fallbacks declare their place in the budget explicitly (the launcher
enforces it; it never retries by itself):

```text
terminal(command=".../hermes-worker.py --route <route> --task-file <task-file> --workdir <exact-workdir> --timeout 600 --attempt-kind retry --task-key <key>", ...)
terminal(command=".../hermes-worker.py --route <next-route> --task-file <task-file> --workdir <exact-workdir> --timeout 600 --attempt-kind fallback --fallback-from <route> --task-key <key>", ...)
```

After a timeout/lost response, verify process, receipt, and diff first, then
add `--reconciled`. Declare `--data-class private` for non-synthetic tasks;
the launcher refuses it on synthetic-public-only routes. A dry-run only
checks configuration — it never proves TUI, web UI, or Brain E2E behavior.

For a configuration-only check:

```text
terminal(command="python bin/hermes-worker.py --route <route> --task \"synthetic dry run\" --workdir <workdir> --dry-run", timeout=30)
```

## Procedure

1. Read only the selected route entry from `worker-catalog.json` and choose the
   route (tool + model + effort) matching difficulty, change risk, data class
   (public/synthetic vs private), tool capability, observed availability/quota,
   and billing source. Defaults: tests/builds run directly (no worker).
   Route in tiers: Tier-1 draft first (`antigravity-normal` Gemini Flash high
   or `codex-normal` Luna/max, `--timeout 180`); escalate to Tier-2 hard
   (`codex-hard`/`codex-terra` Sol/Terra high/xhigh or `antigravity-hard`
   Gemini Pro high, `--timeout 300`) only when Tier-1 stalls on architecture;
   Tier-3 review/paid (`codex-review` Astra/low, `antigravity-review` Opus
   integrated, `opencode-bedrock` Opus high/max) for hard decisions, high-risk
   review, or bounded paid fallback. Never open with the heaviest model for a
   bounded phase. When genuinely torn between two adjacent tiers, choose the
   higher one: over-provisioning costs cents, a wasted budget turn costs a
   full retry cycle. Trivial work Brain can finish directly in under 2 minutes
   (tiny file ops, single-file small edits) stays with Brain: measured
   per-call adapter overhead is 26k+ input tokens even for a 150-char task. Size the task to the tier: one worker call = one phase
   (phase 1: interfaces/main code; phase 2: edge cases/test fixups via a
   resumed session), each under ~2500 task chars and its tier timeout.
   The launcher enforces this: above 2500 chars it warns (receipt
   `size.oversize_warn`), above 6000 chars it refuses without an explicit
   `--size-approval` note. Dense-but-legit payloads (schemas) use the
   approval escape; do not silently chunk one logical task across keys to
   dodge the gate (each key carries its own budget, so dodging only
   multiplies cost).
   Monolithic read-everything-plus-implement-plus-test dispatches are banned.
   These are explainable policies, not IQ rankings.
2. Delegate implementation or review through `bin/hermes-worker.py`. Pass the
   route, task, and exact workdir; do not invent CLI flags from a UI dropdown.
   When continuing a prior worker's session (fixup with test diffs, checkpoint
   2 of a split task), add `--resume-session <worker_session_id>` and
   `--resume-from-job <prior-job_id>` on the same tool; the launcher builds
   the verified resume argv (`codex exec resume`, `agy --conversation`,
   `opencode run --session`) and records `receipt.resume` plus ledger linkage.
   Resume never bypasses attempt budgets. Codex resume requires the catalog
   full-access bypass (currently authorized); cross-tool resume is refused.
   The launcher already appends the worker contract (no worker-side test
   suites; closing Files-changed/Self-check/Verify-with block) to every
   prompt — do NOT repeat it in the task text; that would burn tokens twice.
   When the referenced job is a spawned attempt of the same task-key, the
   launcher verifies the resumed session against the ledger
   (`receipt.resume.verification: verified`) and refuses cross-wired resumes.
   On `--attempt-kind retry` no `--resume-from-job` flag is needed: the
   launcher auto-verifies against this key's latest spawned session.
3. If a provider reports a clearly identified adapter reasoning mismatch, use
   at most one explicit `--reasoning-override` that the catalog allowlists.
   Never switch provider or retry indefinitely. One task: at most 1 retry on
   the same route + 1 fallback route, only for provider-classified errors
   (`failure_class: provider_retryable`). Test failures and review-found bugs
   are task failures, never provider errors. A timeout/lost response with
   possible file mutation: verify process, receipt, and diff first; never run
   a copy. `usage_limit_reached` with a reset marker is
   `quota_exhausted_checkpoint`: preserve the checkpoint and stop short retries,
   credential rotation, and fallback in the same quota bucket. A normal
   transient 429 remains `provider_retryable`. Never reset the ledger or change
   the    task key to bypass this policy. A third spawned attempt on a key with 2
   prior timeouts additionally requires `--timeout-approval` (unified escape
   for expensive time exceptions) AND must change route or shrink scope;
   retrying the identical full-scope task a third time is banned. A Brain-test failure after a succeeded
   worker is NOT a retry of that task: open a new fixup task-key carrying the
   test diff and resume the prior session (see How to Run). Never run two workers writing the same
   worktree.
   Keep the returned background session ID. Wait for completion notification;
   do not launch the job again or poll logs repeatedly. The launcher owns the
   tiered worker deadline; a timeout receipt's progress diagnostics identify
   whether the child was still in a local command/test. Never wrap it in a
   shorter foreground timeout.
4. After the worker exits, inspect its result and the `HERMES_WORKER_RECEIPT`
   line (route/model/effort from→to + reason, `failure_class`, requested vs
   observed model/reasoning, `resume.mode`, timeout `tier`). The launcher also appends one record to `logs/worker_usage.jsonl`.
5. Run tests, builds, or deterministic checks directly with Hermes tools in the
   target workdir. Report their status separately from the worker status.
6. Report the requested and observed model/reasoning, session IDs, elapsed time,
   exit code, test status, and usage fields. `null` means the source did not
   emit a number; it is not zero. On fallback failure, save a checkpoint and
   report a blocker; do not loop.

## Task authoring checklist (first-pass rate is the cheapest token saver)

Every task file states: (1) done-criteria as checkable bullets, (2) explicit
out-of-scope (what NOT to touch), (3) the exact verify command Brain will run
(so the worker writes toward it). Same-key retries reuse byte-identical task
text (key defaults to its hash; identical prefix keeps provider cache affinity).
Total spawned walls per key may not exceed 1200s without `--timeout-approval`.

## Fixup task template (P3-lite: standardized hand-off, no auto-loop)

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

No automatic fixup pipeline exists by design: the launcher records
`receipt.fixup {of, depth}` and ledger linkage, and refuses depth above the
catalog cap. Environment-caused failures (missing dep, bad config) must be
fixed by Brain directly, never auto-resumed.

## Ephemeral worktrees (P1, Brain-created only)

The launcher never creates worktrees. When a dirty workspace is unacceptable
(MoonStorm tasks), Brain isolates with plain git before dispatch:

1. Confirm the target is a git repo: `git -C <repo> rev-parse --is-inside-work-tree`.
   `D:\Hermes` is NOT a git repo — never attempt worktrees there.
2. Pre-register the temp path in `worker-catalog.json`
   `policy.allowed_workdir_roots` first (backup the catalog before editing).
3. Create: `git -C <repo> worktree add -b job-<job_id> <temp-path> <base-ref>`.
4. Dispatch the worker with `--workdir <temp-path>` (same tool/route rules).
5. Run tests directly in `<temp-path>`.
6. PASS → Brain merges `job-<job_id>` into the base branch directly
   (deterministic git op, not worker work). FAIL/TIMEOUT → Brain runs
   `git worktree remove --force <temp-path>` and `git branch -D job-<job_id>`;
   the base stays pristine.
7. Forbidden on the contributor route (exact-workdir lock). Parallel workers
   need distinct pre-registered worktrees; the single-writer lock still
   applies per worktree.

## Fan-out rules (micro proven, macro gated)

Proven: 2 tiny Flash jobs in parallel, distinct keys and dirs, ~15s each,
no 429, no I/O errors, JSONL intact. Allowed only when ALL hold: disjoint
write scopes (never shared files), payload dwarfs the measured 26-38k
per-call overhead (heuristic: no fan-out under ~100 changed lines), and no
key is on its final (3rd) attempt — turn-3 goes sequential, top tier,
single-thread. DAG handoffs carry diffs or summary artifacts only, never raw
history. One job failing freezes only its downstream dependents (fail-fast);
independent branches continue. Heavy parallel work (50k+ token spikes) additionally
requires separate accounts, not just separate dirs — same-account 429 under
spike is unproven either way.

## Outer-ring stubs (P2 pilot: redaction aid, not air gap)

To give contributor/external workers interface context without backend bodies:

1. Brain runs locally: `python bin/hermes-stubgen.py --src <backend.py> --out
   <synthetic_demo/stub.py>` (or `--src-dir/--out-dir` for batch). Python only.
2. Brain reviews the stub output against this checklist before ANY external
   use: no function bodies remain; no secret literals outside defaults; default
   values and decorators inspected line by line (they are preserved verbatim
   and can leak); endpoint paths assessed; stub regenerated if the backend
   changed after generation (stale stubs cause wrong code).
3. Stubs land in `synthetic_demo` only. No new outer-ring dir, no Cline
   integration until the pilot proves leak-free on synthetic tasks.

## Verdict logging and route proxies (no USD inference)
Codex/Antigravity emit no cost, so routes are compared with proxies, never
with raw cross-provider token totals (Codex input already includes cache;
other adapters report raw counters):

- **FPVR (first-pass verification rate)**: share of jobs whose Brain-run
  suite passes first try, no retry/fixup. After running tests, append one
  line per job: `python -c "import json;open('logs/brain_verdicts.jsonl','a').write(json.dumps({'job_id':'<id>','route':'<route>','test_status':'pass|fail'})+'\n')"`.
- **Churn**: lines re-edited across phases per finally-merged line (git repos
  only; N/A under `D:\Hermes`, which is not a repo).
- **Tool-action density**: local commands per successful job, from timeout
  diagnostics and worker output (comparative only, same task family).

## Catalog re-probe (periodic, read-only, no inference)

CLI vendors change model IDs and effort flags per release (this once broke
the Opus route). Quarterly or after any CLI update, re-probe read-only and
snapshot the result into `worker-catalog.json` verification notes:

```text
terminal(command="codex exec --help", timeout=30)
terminal(command="agy --help", timeout=30)
terminal(command="agy models", timeout=60)
```

Never run inference for a probe. If a flag/model changed, update the route
entry plus a deterministic test, not just the docs.

## Model/effort allowlist (enforced by the launcher)

- Codex: Luna = max only; Terra/Sol = low/medium/high/xhigh (never max/ultra);
  Astra = low only. Terra/Astra have no verified catalog route yet: mark
  unavailable, do not invent IDs.
- Antigravity: Flash high and Pro high use `--effort high`. Opus Thinking uses
  integrated reasoning and must omit `--effort`; receipts must say exactly
  `model-integrated/default, effort chưa xác nhận`. Do not call it high/max.
  If that route remains unavailable after the capability fix, report it and
  propose the approved Gemini Pro route; do not silently use Contributor.
- OpenCode: Muse Spark Contributor = xhigh (synthetic/public only, never
  private source/creds); Bedrock Opus = high or max (paid fallback, bounded
  invocations).
- Brain: Sol/high default, Luna/max fallback only. Never apply the worker
  fallback chain to Brain implicitly.

## Pitfalls

- The Brain fallback is configured separately in `config.yaml`; a worker error
  does not authorize provider failover.
- Token fields are source-specific. Codex input includes cache and output
  includes reasoning. Other adapters retain raw counters with explicit unknown
  overlap: do not produce a cross-provider total until semantics are verified.
- Cost is the sum of unique terminal step events, not the first event. It is
  adapter telemetry, not an independently reconciled bill.
- Hermes state.db uses CanonicalUsage: input_tokens is a separate uncached
  bucket; prompt total = input_tokens + cache_read_tokens + cache_write_tokens.
  Do not apply Codex CLI's inclusive-input convention to Brain database rows.
- Antigravity headless can exit zero with denied_actions and an empty response.
  Treat this as blocked. Supervisor has now authorized full-access worker
  invocation in worker-catalog.json; the launcher supplies permission overrides.
  No manual approvals should be required for ordinary worker tools. This is
  not an OS sandbox and does not override account/provider administrative policy.
- Missing usage telemetry stays unknown. Do not infer USD, quota, or a model from
  a successful process exit alone.
- Dry-run proves only allowlist and invocation construction. It is not an
  end-to-end worker pass.
- A pre-inference adapter/model rejection is a configuration/capability
  failure, not a business-task failure or transient provider error. Keep its
  receipt and attempt history; fix the route or choose an approved route.
- Early termination on stagnation is rejected by design: deep-reasoning runs
  are legitimately silent for minutes (a 456s success exists in the log), so
  no kill may precede the declared tier deadline. Stagnation diagnosis uses
  the timeout receipt's `progress_snapshot`, never a watchdog kill. A
  streaming stdout reader was evaluated and CUT for the same reason plus
  Windows pipe risks and zero gain on single-JSON adapters; revisit only with
  new evidence.
- Orphan cleanup already tree-kills (`taskkill /T /F` with ownership check);
  a Job Object wrapper remains deferred hardening for the launcher-crash case
  only, never a live fire.
- Stub files go stale when the backend changes; regenerate per use and never
  trust a stub older than its source.

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
