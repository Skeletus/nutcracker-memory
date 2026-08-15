# Implementation notes and research backlog

This document is the technical entry point for future implementation work. The
[curated scientific knowledge base](nutcracker_scientific_memory_curated.md)
remains the source of truth. Every item below is an engineering hypothesis to
test, not a claim that the software recreates a biological algorithm.

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

## Design decision matrix

This matrix carries forward Section 10 of the curated source.

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
