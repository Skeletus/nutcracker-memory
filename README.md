# nutcracker-memory

`nutcracker-memory` is a persistent memory engine for coding agents, initially
intended for Codex CLI through the Model Context Protocol (MCP). It is designed
to retain architectural decisions, investigated bugs, failed approaches, and
repository context across sessions.

Generic text memory can retrieve a semantically similar note without knowing
whether the code that made the note true still exists. This creates context
drift: an old architectural decision can look relevant even after its module,
dependencies, or validation path changed. The current MVP anchors Episodes to
explicit repository-relative files, records complete-file hashes, and checks
those hashes during recall so semantic relevance and current file integrity
remain separate signals.

## Quick start

Nutcracker is a standard Python package with a cross-platform CLI. Install it
once with [uv](https://docs.astral.sh/uv/), then initialize it from the
repository whose history you want to manage:

```text
uv tool install git+https://github.com/Skeletus/nutcracker-memory.git
cd my-project
nutcracker init
nutcracker doctor
```

`nutcracker init` detects the Git root (or uses the current directory with a
warning when Git is unavailable), creates a repository-local
`.nutcracker/memory.db`, adds `.nutcracker/` to `.gitignore`, installs a
marker-delimited Nutcracker policy block in `AGENTS.md`, and registers an MCP
server for that repository through Codex's supported `codex mcp add` command.
No manual edit of `config.toml`, `NUTCRACKER_REPO_ROOT`, or
`NUTCRACKER_DB_PATH` is required.

One MCP registration intentionally serves one repository. Its readable name
contains the repository basename and a stable short hash of its resolved path,
which prevents collisions between repositories with the same name. Run
`nutcracker init` from each repository you want to use independently.

Codex registers these MCP servers globally for the current user. Therefore,
initializing several repositories creates several global Nutcracker entries.
If a repository is moved or renamed, its old entry can become stale; remove it
with `codex mcp remove <old-name>` and run `nutcracker init` again from the
new location.

Codex CLI must already be installed and available on `PATH`. The first actual
memory save or recall may take longer because FastEmbed lazily downloads the
configured `BAAI/bge-small-en-v1.5` embedding model. It needs network access
only while that model is absent from FastEmbed's local cache.

The broader research direction may later combine episodic records with a
repository graph, structural-neighborhood retrieval, and Git-aware identity.
Those capabilities are not part of the current MVP. Elapsed time is not used
as a hard time-to-live rule.

## Scientific grounding

Nutcracker Memory is **bio-inspired engineering**, not a reproduction of a
known biological algorithm. In the precise language of the curated source:

> Nutcracker explores a computational memory architecture inspired by
> experimentally observed properties of spatial memory in Clark's
> nutcrackers, including multi-landmark encoding, reliance on stable
> structural cues, long-term persistence, and flexible cue use.

The source set motivates these engineering hypotheses:

- Clark's nutcrackers use spatial information to recover caches; recovery
  cannot be reduced to detecting the cached seed. This motivates anchoring a
  memory to an environment model instead of storing only free text.
- Multiple landmarks can preserve search accuracy when another spatial cue is
  experimentally made unreliable. This motivates redundant, multi-anchor
  episode encoding, while not claiming a known neural representation.
- Broad, stable environmental structure can matter, and simply adding
  arbitrary local objects does not necessarily improve recovery. This informs
  future experiments with stability-aware anchors; the current MVP weights all
  file anchors equally.
- Cache-location memory remained above chance at intervals up to 285 days, but
  the longest interval showed evidence consistent with some forgetting. This
  argues against both aggressive TTL deletion and claims of perfect temporal
  permanence.

Applegate and Aronov's work concerns **black-capped chickadees**, not Clark's
nutcrackers. It is used only as comparative evidence that mnemonic and
non-mnemonic strategies can be combined flexibly.

Read the [complete curated scientific basis](docs/nutcracker_scientific_memory_curated.md)
for evidence levels, limitations, and references.

## Future direction

The research direction may later explore symbol-level anchors,
rename-resistant identity, stability-aware anchor weighting, repository maps,
and structural-neighborhood retrieval. These are engineering hypotheses, not
current capabilities; the technical roadmap is in [docs/README.md](docs/README.md).

## What this is NOT

- It is not an exact reproduction of avian memory, and it does not claim to
  implement "the Clark's nutcracker algorithm"; no complete algorithm is known
  from the cited literature.
- It is not a claim that memories never decay with time. Any temporal signal
  must be tested experimentally and must not substitute for structural
  validation.
- It is not a replacement for structural code-graph tools such as
  `codebase-memory-mcp`. Those tools model code structure; this project is
  intended to complement that layer with persistent episodic memory tied to
  the structure.

## Status

The current MVP implements Episode persistence in SQLite, summary embeddings,
cosine-similarity retrieval, explicit file anchors, complete-file hash
revalidation, equal-weight anchor integrity, structural trust/fallback status,
and `memory_save`/`memory_recall` over MCP stdio. `nutcracker init` also
installs an agent policy that guides proactive recall/save decisions, but that
policy is guidance rather than a guarantee that every agent session will call
the tools.

It does not implement a repository graph, AST or symbol intelligence,
structural-neighborhood retrieval, rename detection, Git-aware reconciliation,
semantic contradiction detection, adaptive landmark weighting, or automatic
fallback exploration. A changed hash proves that file bytes changed; it does
not prove that the historical decision became invalid.

Implementation guidance and the experiment backlog are in [docs/README.md](docs/README.md).
