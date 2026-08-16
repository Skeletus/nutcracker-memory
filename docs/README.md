# Implementation notes and research backlog

This document is the technical entry point for future implementation work. The
[curated scientific knowledge base](nutcracker_scientific_memory_curated.md)
remains the source of truth. Every item below is an engineering hypothesis to
test, not a claim that the software recreates a biological algorithm.

## What the MVP actually implements

The current MVP provides persistent episodic memory through the `Episode`
model and SQLite. The normal `memory_save` path requires one or more explicit
anchors, where each anchor currently means a repository-relative **file path**.
Nutcracker hashes the complete contents of every anchored file with SHA-256,
persists the Episode and its baseline hashes, and embeds only the Episode
`summary` for semantic retrieval. Episode persistence and embedding
persistence are currently separate writes rather than one atomic transaction.

During `memory_recall`, Nutcracker embeds the query, calculates cosine
similarity against persisted summary embeddings, and applies
`min_similarity` to that semantic signal. It then re-reads each candidate's
anchored files and classifies the current file state as:

- `VALID`: the file exists and its complete-content hash matches;
- `CHANGED`: the file exists but its complete-content hash differs;
- `MISSING`: the file no longer exists at the stored path.

For each candidate:

```text
anchor_integrity = valid_anchors / total_anchors
score = semantic_similarity * anchor_integrity
```

An Episode is `structurally_valid` only when it has at least one anchor and
all its anchors are currently `VALID`. Recall ranks candidates by score, then
semantic similarity, with a stable Episode-ID tie-break. It returns one of
three response states:

- `FOUND`: at least one semantic candidate is completely structurally valid;
- `FALLBACK_REQUIRED`: semantic candidates exist, but none is completely
  structurally valid;
- `NO_MATCH`: no stored embedding passes the semantic filter.

Drift evaluation produces current copies of the anchors for the recall result.
It does not rewrite the persisted historical Episode, its baseline hashes, or
its original verification state.

The MVP's present value proposition is that **semantic relevance and
structural trust are separate questions**. It asks both:

```text
Is this memory relevant to the query?
Is the file context that supported this memory still byte-for-byte intact?
```

The second question is deliberately narrower than semantic correctness.
Nutcracker detects file-level drift; it does not prove that a changed file
invalidates the historical conclusion, or that an unchanged anchored file
means every relevant program assumption remains true.

## Bio-inspired motivation

The curated literature motivates investigating persistent memory associated
with environmental cues, the use of multiple landmarks, robustness when one
cue becomes unreliable, and the importance of broad stable structure. It does
not provide a complete biological or computational algorithm for Clark's
nutcracker memory.

The MVP uses the following **computational analogies**:

| Biological inspiration | Current engineering analogue |
| --- | --- |
| Memory of a cache | `Episode` |
| Contextual cue or landmark | File `Anchor` |
| Multiple cues | Multiple anchors on one Episode |
| Surviving cues after environmental change | Fraction of anchors still `VALID` |
| Persistent historical location memory | Persisted Episode and baseline hashes |
| Current environmental state | File revalidation during recall |

These mappings are engineering hypotheses inspired by behavioral findings,
not demonstrated biological equivalences. Nutcracker explores whether
principles inspired by landmark- and cue-dependent memory can improve
persistent memory for coding agents. It does not model the bird's brain or
claim biological accuracy. Applegate and Aronov's findings about flexible
memory use concern black-capped chickadees and remain comparative evidence,
not direct evidence about Clark's nutcrackers.

## Implementation status

| Concept | MVP status | Notes |
| --- | --- | --- |
| Episodic memories | Implemented | `Episode` model plus SQLite persistence |
| Semantic recall | Implemented | Summary embeddings plus cosine similarity |
| File anchors | Implemented | Repository-relative file paths plus complete-content hashes in the MCP path |
| Multi-anchor memories | Implemented | The normal save path accepts multiple anchors per Episode |
| Drift detection | Implemented | Recall generates `VALID`, `CHANGED`, or `MISSING` from current file contents |
| Partial cue survival | Partial | Surviving anchors affect integrity and score, but complete trust still requires every anchor to be `VALID` |
| Historical/current-state separation | Implemented | Recall returns current anchor copies without rewriting the persisted Episode |
| Landmark hierarchy | Schema only | `AnchorLevel` exists but does not affect retrieval or scoring |
| `MemoryStrength` | Schema only | Its fields exist but are not active in recall or scoring |
| Anchor relations | Schema only | `AnchorRelation` persists how an anchor was used, but does not affect retrieval or scoring |
| Episode lifecycle fields | Schema only | Contradiction, supersession, retrieval-tracking, and outcome fields persist but have no automatic MVP behavior |
| Symbol-level anchors | Not implemented | `symbol` currently means a relative file path, not a function, class, or AST symbol |
| Rename detection | Not implemented | A moved file normally appears as `MISSING`; `RENAMED` is not generated automatically |
| Structural repository map | Not implemented | There is no AST, graph, call topology, or import topology |
| Structural-neighborhood recall | Not implemented | Candidate retrieval is semantic-first and scans stored embeddings |
| Flexible cue weighting | Not implemented | Every anchor contributes equally, regardless of level or relation |
| Automatic fallback exploration | Not implemented | `FALLBACK_REQUIRED` is a signal returned to the caller, not an action |

## What this is NOT

The current MVP is not:

- an implementation of a complete "Clark's nutcracker memory algorithm";
  no such complete algorithm is known from the curated literature;
- a neurobiological model or a biologically accurate reproduction of avian
  memory;
- a complete cognitive map of a repository;
- an AST- or graph-based code-intelligence engine;
- a detector of semantic invalidation;
- a system that understands automatically whether a code change contradicts
  a historical memory;
- a rename-detection system;
- a system with a functional landmark-stability hierarchy;
- a system with flexible or learned cue weighting;
- a replacement for comprehensive codebase-intelligence tools.

The current resolver establishes only:

```text
file bytes changed
        -> CHANGED
```

It cannot establish:

```text
relevant program semantics changed
        -> previous decision is invalid
```

Consequently, formatting, comments, generated output, or another irrelevant
byte-level edit can mark an anchor `CHANGED` even when the historical decision
remains valid. Conversely, a decision can become obsolete because of an
unanchored dependency while every stored anchor remains byte-for-byte intact.

## Engineering choices — not biological claims

The following are project-specific engineering decisions. The scientific
source motivates investigating multi-cue, landmark-dependent, persistent
retrieval, but it does not prescribe these mechanisms:

- SHA-256 of complete files as the integrity baseline;
- repository-relative file paths as anchors;
- embeddings of Episode summaries;
- cosine similarity for semantic relevance;
- `anchor_integrity = valid_anchors / total_anchors`;
- `score = semantic_similarity * anchor_integrity`;
- requiring all anchors to be `VALID` for `structurally_valid=True`;
- the `FOUND`, `FALLBACK_REQUIRED`, and `NO_MATCH` response states;
- SQLite persistence and float32 BLOB embedding storage;
- the `AnchorRelation` categories;
- preserving the historical Episode without rewriting it during recall.

These choices should be evaluated against simpler baselines. They must not be
described as neural mechanisms, avian representations, or rules recovered
directly from Clark's nutcracker behavior.

## Schema and future modeling fields

The `Episode` schema intentionally preserves several fields that are not active
MVP behavior. They can be serialized and persisted, but Nutcracker does not
automatically update them and they do not affect retrieval or scoring:

- `MemoryStrength` (`anchor_integrity`, `retrieval_success`, and
  `outcome_support`);
- `AnchorLevel` and `AnchorRelation`;
- `EpisodeState.contradicted`, `superseded_by`, `retrieval_count`, and
  `last_retrieved_at`;
- `Outcome` and its test/outcome annotations.

These fields reserve explicit representation for future experiments. They do
not implement contradiction detection, supersession, retrieval reinforcement,
or outcome-weighted scoring in the current MVP.

`EpisodeState.structurally_valid` is historical persisted state, not a value
automatically synchronized at recall. `memory_recall` resolves anchors against
the current repository and returns a separate, current
`RecallResult.structurally_valid`. That current interpretation does not rewrite
the stored Episode, its baseline hashes, or its persisted state.

## Why the conservative trust policy?

An Episode with three of four anchors still `VALID` remains discoverable and
receives:

```text
anchor_integrity = 3 / 4 = 0.75
```

However, the MVP sets:

```text
structurally_valid = False
```

because complete structural trust currently requires every anchor to remain
`VALID`. If no other fully valid candidate exists, recall therefore returns
`FALLBACK_REQUIRED` while retaining the partially drifted Episode as
diagnostic context. This is a deliberately conservative MVP policy, not a
rule derived from Clark's nutcracker behavior. Whether surviving cues should
support partial or complete trust is an open experimental question.

## MVP hypothesis

The concrete question for this MVP is:

> **Does file-anchor revalidation reduce the use of stale memories compared
> with semantic-only recall without producing too many false warnings?**

This is a hypothesis to test through measurable agent behavior, not a
demonstrated conclusion. The project question is not how faithfully the
software reproduces Clark's nutcracker memory. Biological evidence motivates
candidate computational principles; comparative experiments must establish
whether the resulting engineering mechanism is useful.

## Future work

Future work should address observed MVP limitations incrementally rather than
attempting unspecified biological fidelity:

1. symbol-level anchors that tolerate irrelevant file changes;
2. rename-resistant anchor identity;
3. hierarchical anchors with functional structural meaning;
4. a structural repository map;
5. structural-neighborhood retrieval;
6. differentiated confidence or weighting between cues;
7. experimentally evaluated trust policies;
8. real exploratory fallback performed by an appropriate caller or later
   integration layer.

Each item is a future engineering hypothesis. None is required merely to make
the software resemble a biological system.

## Research hypothesis backlog

The hypotheses from Section 8 define the experimental backlog. None is treated
as validated for coding-agent memory before comparative evaluation.

| ID | Hypothesis | Experiment target |
| --- | --- | --- |
| H1 | Multi-anchor encoding | Test whether memories attached to several structural anchors survive refactors better than single-symbol or single-path memories. |
| H2 | Structural retrieval | Compare graph proximity plus semantic similarity with vector similarity alone for task-relevant historical recall. |
| H3 | Stable-landmark weighting | Measure whether stronger architecture-level weighting reduces stale-memory use after refactoring. |
| H4 | Event-driven encoding | Compare memories formed at salient task events with storage of every conversational turn for signal-to-noise ratio. |
| H5 | Structural drift | Compare anchor validity derived from real repository changes with a simple TTL policy. |
| H6 | Cue redundancy | Measure whether several surviving anchors preserve usefulness when one anchor becomes invalid. |
| H7 | Location/state separation | Test whether separating structural identity from mutable episode state avoids incorrect deletion or suppression of useful history. |

Experiments should include simpler baselines: no persistent memory, vector
memory, and a code knowledge graph. Useful measures include task success,
repeated errors, relevant and irrelevant retrieval, stale-memory use, token and
tool cost, files inspected, and completion time.

## Research design decision matrix

This matrix carries forward Section 10 of the curated source. It records
research directions and constraints, not the implementation status of the
current MVP; the status table above is authoritative for shipped behavior.

| Decision | Current support | Implementation stance |
| --- | --- | --- |
| Persistent episodic memory | Supported direction | Implement and benchmark event-oriented episodes. |
| Repository graph / cognitive map | Supported engineering abstraction | Use real repository structure as the environment to which episodes are anchored. |
| Multiple anchors per episode | Supported direction | Preserve redundant structural, regional, local, and validation anchors. |
| Landmark stability hierarchy | Supported direction | Distinguish high-, medium-, and low-stability repository landmarks. |
| Structural-neighborhood retrieval | Supported direction | Use graph proximity alongside semantic retrieval. |
| Explicit memory state | Supported direction | Keep episode identity separate from mutable validity and outcome state. |
| Git-based structural drift | Supported engineering abstraction | Revalidate anchors against code change and degrade confidence gracefully. |
| Semantic retrieval | Supported as one cue | Combine it with structural evidence rather than treating it as sufficient. |
| Event-driven memory creation | Plausible hypothesis | Encode salient events and validate the signal/noise benefit experimentally. |
| Aggressive TTL deletion | Not justified | Do not implement as a biological default. |
| Automatic decay solely from elapsed time | Not justified | If evaluated, treat age as an optional weak feature rather than a dominant rule. |
| Suppression after first retrieval | Not justified | Do not equate retrieval with consumption or forgetting. |
| Equal stability for every symbol | Not justified | Preserve an explicit stability hierarchy. |
| Exact reconstruction of avian memory | False / not justified | Always describe the project as bio-inspired engineering. |
| Known neural or computational algorithm | False / not justified | Do not claim one exists in the source set. |

## Unresolved questions

All questions in Section 11 remain open. The current papers do not resolve the
neural code for cache locations, how representations are separated, exact cue
weights, consolidation, a mathematical forgetting function, long-term landmark
recognition, hippocampal roles, whether a graph is the right computational
analogue, or whether these abstractions improve LLM-agent performance.

Future design decisions must label assumptions about those questions as
experimental proposals. They must not silently promote them to scientific
facts. In particular, scoring coefficients, drift rules, consolidation policy,
and any temporal prior require empirical validation.
