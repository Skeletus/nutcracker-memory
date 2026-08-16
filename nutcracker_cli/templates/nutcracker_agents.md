## Nutcracker persistent memory

This repository has the Nutcracker persistent-memory MCP server. Use it to
preserve or recover durable project context, not as a replacement for reading
current code.

- Before a non-trivial decision about a module or subsystem, consider
  `memory_recall` when prior decisions, investigated bugs, rejected approaches,
  or conventions could affect the work.
- Do not call `memory_recall` for trivial, self-contained edits or when the
  required information is already evident in the current context.
- Save with `memory_save` after producing durable technical knowledge: a
  non-trivial architectural decision and rationale, a non-obvious bug cause, an
  important constraint, or a rejected reasonable approach and its reason.
- At the end of every task, evaluate whether such durable knowledge was
  produced. If so, call `memory_save` before finishing; saving remains
  conditional, not automatic.
- Do not save typos, formatting, trivial renames, mechanical progress, or facts
  obvious from the current code.
- `FALLBACK_REQUIRED` means related memories were found but their structural
  context is degraded; inspect the current repository before relying on them.

Prioritize signal over quantity. Nutcracker is a bio-inspired engineering
abstraction, not a literal biological model or an infallible repository map.
