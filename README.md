# nutcracker-memory

`nutcracker-memory` is a persistent memory engine for coding agents, initially
intended for Codex CLI through the Model Context Protocol (MCP). It is designed
to retain architectural decisions, investigated bugs, failed approaches, and
repository context across sessions.

Generic text memory can retrieve a semantically similar note without knowing
whether the code that made the note true still exists. This creates context
drift: an old architectural decision can look relevant even after its module,
dependencies, or validation path changed. Nutcracker Memory proposes anchoring
episodes to the repository's actual structure and tracking whether those
anchors remain trustworthy as the code evolves.

The planned system combines episodic records, a repository graph, semantic
retrieval, and Git-based structural drift. Structural validity is the primary
signal for continued trust; elapsed time may later be evaluated as a weak,
optional feature, not imposed as a hard time-to-live rule.

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
  arbitrary local objects does not necessarily improve recovery. This
  motivates weighting durable repository structure more strongly than volatile
  line-level details.
- Cache-location memory remained above chance at intervals up to 285 days, but
  the longest interval showed evidence consistent with some forgetting. This
  argues against both aggressive TTL deletion and claims of perfect temporal
  permanence.

Applegate and Aronov's work concerns **black-capped chickadees**, not Clark's
nutcrackers. It is used only as comparative evidence that mnemonic and
non-mnemonic strategies can be combined flexibly.

Read the [complete curated scientific basis](docs/nutcracker_scientific_memory_curated.md)
for evidence levels, limitations, and references.

## Proposed architecture

The following is an engineering abstraction motivated by the source set:

```text
Current task + repository position + Git state
                     |
                     v
       Repository graph G = (V, E)
       nodes: repo/package/module/file/symbol/test/service
       edges: contains/imports/calls/tests/depends_on/...
                     |
          bounded structural neighborhood
                     |
                     v
  +--------------------------------------------------+
  | Episode                                          |
  | summary + observations + decision + outcome     |
  | provenance + explicit validity/state            |
  |                                                  |
  | multi-anchor encoding (no single canonical one) |
  |   +-- structural: repository/module/API          |
  |   +-- regional:   class/service/route/test suite |
  |   `-- local:      function/line/local detail     |
  +--------------------------------------------------+
                     |
       semantic relevance + structural support
                     |
                     v
       structural drift reconciliation via Git
       unchanged / moved / partial / contradicted / gone
                     |
                     v
              compact retrieved context

Landmark stability hierarchy

  HIGH    repository, bounded context, module, public API, schema
    |     expected to provide durable structural context
  MEDIUM  class, service, interface, route, test suite
    |     useful regional context with moderate volatility
  LOW     function detail, line number, local variable, file offset
          precise but fragile local context
```

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

Initial scaffold only. The repository contains documentation and module
boundaries, but no memory engine, retrieval algorithm, scoring implementation,
storage integration, or MCP tools yet.

Implementation guidance and the experiment backlog are in [docs/README.md](docs/README.md).
