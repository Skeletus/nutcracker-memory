# Project instructions

## Persistent memory policy

### Context

This project has a persistent-memory MCP server named `nutcracker`. Its role
is to preserve durable knowledge across sessions, including:

- architecture decisions and their rationale;
- non-obvious causes of resolved bugs;
- important constraints discovered during development;
- reasonable approaches that were evaluated and rejected.

Nutcracker is a bio-inspired engineering abstraction, not a literal
reproduction of Clark's nutcracker memory or of a known biological algorithm.

### `memory_recall` policy

Consider calling `memory_recall` before making a non-trivial decision about a
file, module, or subsystem when there is a reasonable signal that historical
context could affect the current decision.

Also consider it when the task requires understanding why part of the system
was designed in a particular way, or when the current decision may depend on
decisions made in earlier sessions.

Do not call `memory_recall` merely because:

- a file appears for the first time in the current session;
- you are about to read or edit a file;
- the requested change is trivial;
- the necessary information is already evident from the current context.

The intent is to consult persistent context when project history could change
or enrich a decision, not before every code operation.

### `memory_save` policy

Consider calling `memory_save` after producing knowledge likely to be useful
in future sessions, especially:

- a non-trivial architecture decision and its rationale;
- the non-obvious cause of a bug;
- an important constraint discovered during investigation;
- a reasonable approach that was evaluated and rejected, together with why.

Do not save:

- typos;
- formatting changes;
- trivial renames;
- facts obvious from reading the current code;
- temporary details of the current session;
- redundant information without likely future value.

Prioritize signal over quantity.

### End-of-task memory checkpoint

At the end of every task, just before considering it complete, evaluate
whether the work produced durable technical knowledge likely to be useful in
future sessions. Examples include:

- a non-trivial architecture decision and its rationale;
- the non-obvious cause of a bug;
- an important constraint discovered during investigation;
- a reasonable approach that was evaluated and rejected, together with why.

If the task produced such a conclusion, call `memory_save` before finishing
without waiting for the user to request it. Do not call `memory_save` for
typos, formatting, trivial renames, temporary progress, mechanical changes,
or facts obvious from reading the current code.

Always perform the checkpoint evaluation; saving remains conditional. The
goal is to evaluate at every task boundary, not to save after every task.

### Safeguard against overuse

Do not use Nutcracker automatically for every file, edit, or action. Each call
must have a reason related to preserving or recovering useful historical
context. An indiscriminate increase in recalls or saves is not an improvement.

Treat recalled results according to their reported structural status. The MVP
does not provide perfect or infallible memory, complete repository
understanding, or perfect change detection.
