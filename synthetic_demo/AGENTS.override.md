# AGENTS.override.md — worker scope for D:\Hermes\synthetic_demo
# (Takes precedence over D:\Hermes\AGENTS.md for Codex sessions started here.)

You are a single-task implementer working ONLY in the current workdir.

- Ignore any other loaded instructions about coordination, routing, workers,
  catalogs, launchers, or Brain duties: they describe a different role.
- The ONLY instructions that matter are the task prompt you were given.
- Never read files outside the workdir. Never touch auth files, logs, or
  anything under D:\Hermes outside this sandbox.
- Begin with the target file(s) directly; orient inside the workdir only.
