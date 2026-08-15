# Clark's Nutcracker Spatial Memory

## Curated scientific knowledge base for the Nutcracker Memory project

> **Purpose.** This document distills the uploaded papers into
> design-relevant scientific claims for a bio-inspired memory system for
> AI agents. It is **not** a claim that the Clark's nutcracker
> implements a known computer algorithm. The biological mechanism is
> only partially understood. Each proposed software principle below is
> therefore labeled as an **engineering abstraction**, not as a
> biological fact.

------------------------------------------------------------------------

## 1. Source set and scope

This knowledge base is based on the five uploaded PDFs. Four files
represent three Clark's nutcracker studies (one 1988 paper was uploaded
twice), and one paper studies black-capped chickadees and is used only
as comparative evidence about food-caching bird memory.

### S1 --- Balda & Kamil (1988)

**The spatial memory of Clark's nutcrackers (*Nucifraga columbiana*) in
an analogue of the radial arm maze.**\
*Animal Learning & Behavior*, 16(2), 116--122.

**Role in this project:** distinguishes ordinary/working spatial memory
from the unusually persistent memory associated with self-made caches.
The experiment found strong retention through hours but performance near
chance after 24 h in the radial-maze analogue. The authors explicitly
consider the possibility that cache creation recruits a different memory
process.

> Uploaded twice as `fulltext.pdf` and the second copy supplied with the
> source set.

### S2 --- Balda & Kamil (1992)

**Long-term spatial memory in Clark's nutcracker, *Nucifraga
columbiana*.**\
*Animal Behaviour*, 44, 761--769.\
DOI: `10.1016/S0003-3472(05)80302-1`

**Role in this project:** strongest source here for long-term
persistence and non-uniform forgetting. Birds were tested after 11, 82,
183, and 285 days.

### S3 --- Bednekoff & Balda (2014)

**Clark's nutcracker spatial memory: The importance of large, structural
cues.**\
*Behavioural Processes*, 102, 12--17.\
DOI: `10.1016/j.beproc.2013.12.004`

**Role in this project:** strongest source here for cue hierarchy,
environmental robustness, and the importance of stable structural
information rather than arbitrary local detail.

### S4 --- Kelly, Cheng, Balda & Kamil (2019)

**Effects of sun compass error on spatial search by Clark's
nutcrackers.**\
*Integrative Zoology*, 14, 172--181.\
DOI: `10.1111/1749-4877.12302`

**Role in this project:** strongest source here for multi-cue encoding,
redundancy, flexible cue weighting, and the **multiple bearings
hypothesis**.

### S5 --- Applegate & Aronov (2022)

**Flexible use of memory by food-caching birds.**\
*eLife*, 10:e70600.\
DOI: `10.7554/eLife.70600`

**Important scope warning:** this paper studies **black-capped
chickadees (*Poecile atricapillus*)**, not Clark's nutcrackers. It
should not be cited as direct evidence about Clark's nutcracker biology.

**Role in this project:** comparative evidence that a food-caching bird
can combine mnemonic and non-mnemonic strategies, remember both site
contents and previously checked sites, and use the same stored
information differently depending on behavioral context.

------------------------------------------------------------------------

# 2. What the uploaded literature actually supports

## 2.1 Cache locations are represented spatially

The evidence strongly supports the proposition that Clark's nutcrackers
use **spatial memory** rather than simply detecting the seed itself.

Balda & Kamil (1992) summarize earlier experiments in which birds could
relocate cache sites after seeds had been removed and report that moving
or removing landmarks can disrupt recovery. This rules against a simple
model in which retrieval is driven only by sensory traces from the
cached food.

### Confidence

**Strongly supported.**

### Engineering abstraction

A memory should be anchored to a representation of the environment
rather than stored only as free text.

For a coding agent:

``` text
Biology                     Software abstraction

environment                 repository
cache location              code region / symbol
landmark                    stable structural entity
spatial relationship        graph relationship
cache memory                episode / decision / observation
search for cache            context retrieval
```

A memory such as:

``` text
"Changing JwtService caused three authentication tests to fail."
```

should therefore not exist only as an embedding. It can also be anchored
to:

``` text
Repository
└── Auth
    ├── JwtService
    ├── SessionRepository
    └── auth tests
         └── Episode #184
```

**This mapping is an engineering hypothesis, not a finding of the
papers.**

------------------------------------------------------------------------

## 2.2 The system does not appear to depend on one landmark

The 2019 paper provides an especially useful computational hypothesis:
the **multiple bearings hypothesis**, originally proposed by Kamil &
Cheng.

In this model, the bird can encode a cache relative to **several
landmarks**, with bearings containing distance and directional
information.

Conceptually:

``` text
             Landmark A
                 ▲
                /|
               / |
              /  |
             ● CACHE ─────────► Landmark B
              \
               \
                ▼
             Landmark C
```

The cache is therefore not necessarily represented as:

``` text
cache = absolute_coordinate(x, y)
```

or:

``` text
cache = nearest_landmark
```

but potentially through a redundant set of relationships:

``` text
cache = {
    relation_to(A),
    relation_to(B),
    relation_to(C)
}
```

Kelly et al. found that inducing a small sun-compass error significantly
reduced search accuracy when only **one landmark** was available, but
not when **four landmarks** were available.

### Confidence

**Strong evidence for flexible use of multiple spatial cues.**\
**The exact internal neural representation remains unresolved.**

### Engineering abstraction: multi-anchor memory

Do not attach an episode to only one symbol.

Instead:

``` yaml
episode:
  id: E184
  summary: "Refresh token expiration bug"

  anchors:
    - symbol: AuthService.refreshToken
      relation: primary
    - symbol: SessionRepository
      relation: modified
    - symbol: RedisSessionStore
      relation: dependency
    - symbol: AuthIntegrationTests
      relation: validation

  outcome: success
```

This creates redundancy. If `AuthService.refreshToken()` is renamed or
moved, other anchors may still permit recovery.

------------------------------------------------------------------------

## 2.3 Redundant landmarks can compensate for an unreliable cue

The clock-shift experiment is particularly important.

With one landmark, a manipulated sun compass increased search error.
With four landmarks, the clock shift did not significantly impair search
accuracy. The authors conclude that landmark arrays and sun-compass
information interact and that the birds use these sources flexibly.

This does **not** prove a generic biological algorithm such as "always
choose the majority of landmarks." It does demonstrate that the
navigation system can remain accurate when one information source
becomes unreliable and multiple stable cues remain available.

### Engineering abstraction: fault-tolerant retrieval

For Nutcracker Memory, retrieval should not depend on a single
identifier.

Suppose a memory was encoded around:

``` text
AuthService.refreshToken()
SessionRepository.save()
Redis
/auth/refresh
```

After refactoring:

``` text
AuthService.refreshToken()  -> renamed
SessionRepository.save()    -> still exists
Redis                       -> still exists
/auth/refresh               -> still exists
```

The memory should remain discoverable because several anchors survive.

A candidate score could eventually include:

``` text
anchor_support =
    surviving_anchor_count
    + structural_consistency
    + relation_consistency
```

Again, the formula itself is **not biological evidence**. It is a
software design inspired by the demonstrated value of multiple cues.

------------------------------------------------------------------------

## 2.4 Stable structural cues appear more important than arbitrary detail

Bednekoff & Balda (2014) is central to the project.

Previous work summarized in the paper showed that:

-   raking or changing substrate details did not necessarily destroy
    recovery accuracy;
-   birds could recover caches even when the pattern of available
    sand-filled cups/wooden plugs differed dramatically;
-   moving nearby objects could shift search behavior, showing that
    local objects can matter;
-   nevertheless, birds sometimes continued searching at the original
    cache position despite moved nearby objects, implying use of
    additional cues.

The authors' own experiments found:

1.  adding more floor objects to a large room did not significantly
    improve recovery;
2.  subdividing the large room with panels did not significantly improve
    recovery;
3.  birds were significantly more accurate in the small experimental
    room than in the large room.

They interpret the overall evidence as suggesting that **large, stable
structural properties of the environment** can function as important
landmarks.

The ecological argument is intuitive but should be kept separate from
the direct experimental result: snow, wind, gravity, and rockslides can
obscure or move small nearby features, while large structures are more
reliable.

### Confidence

**Strong evidence that simply adding more local objects is insufficient
and that broader environmental structure matters.**\
The precise representation and weighting of "structural cues" is **not
known**.

### Engineering abstraction: landmark hierarchy

Not every code entity should have equal stability.

Possible hierarchy:

``` text
HIGH-STABILITY LANDMARKS
repository
package / bounded context
module
public API
database schema
architectural boundary

MEDIUM-STABILITY LANDMARKS
class
service
interface
route
test suite

LOW-STABILITY LANDMARKS
local variable
line number
temporary helper
exact file offset
formatting
```

A memory should preferentially preserve relationships to
higher-stability landmarks while retaining local anchors for precision.

This is one of the strongest bio-inspired design principles available
from the uploaded literature.

------------------------------------------------------------------------

## 2.5 Local cues are useful, but should not be treated as the whole map

The Bednekoff & Balda review of earlier manipulation experiments shows a
mixed pattern: moving local objects often moved the birds' search, but
some searches remained tied to the original location.

Therefore, the evidence does **not** justify either extreme:

``` text
"Nutcrackers ignore local landmarks."        ❌
```

or:

``` text
"Nutcrackers navigate only by local landmarks." ❌
```

A better characterization is:

> Cache recovery can use multiple levels and sources of spatial
> information, and cue use is flexible.

### Engineering implication

Nutcracker Memory should combine:

``` text
local precision
+
structural/global context
```

For example:

``` text
global:
Auth module

regional:
Session subsystem

local:
SessionRepository.rotateRefreshToken()

episode:
Bug #184
```

If the local function disappears, retrieval can fall back to the
regional/global anchors.

------------------------------------------------------------------------

## 2.6 Long-term cache memory is remarkably persistent, but it is incorrect to say that it never decays

This corrects an important claim from the earlier discussion.

Balda & Kamil (1992) tested birds after:

``` text
11 days
82 days
183 days
285 days
```

Performance remained significantly above random search at every
interval. There were no significant group differences in percentage of
correct probes across the four retention groups.

However, the 285-day group:

-   made more errors during the final recovery session;
-   took longer to locate caches;
-   showed evidence consistent with some forgetting between 183 and 285
    days.

Therefore:

``` text
"Memory does not decay with time."          ❌ unsupported / too strong

"Cache-location memory can remain useful
for many months, with evidence of some
forgetting at very long intervals."         ✅ supported
```

### Engineering implication

A naive TTL such as:

``` python
if memory.age > 30_days:
    delete(memory)
```

is **not biologically motivated by these papers**.

But the opposite rule---

``` python
age never matters
```

---is also not supported.

A safer initial design is:

``` text
memory validity =
    structural validity
    + retrieval evidence
    + outcome evidence
    + optional weak age prior
```

with structural change being treated separately from elapsed time.

The strength of temporal decay should be an **experimental parameter**,
not assumed from the biology.

------------------------------------------------------------------------

## 2.7 Forgetting may be non-uniform: some caches appear better remembered than others

Balda & Kamil (1992) report an important pattern.

Accuracy declined across successive recovery sessions. Earlier work had
found that this decline disappeared when experimenters randomized
recovery order instead of allowing the birds to choose it.

The authors therefore suggest:

> some caches are remembered better than others, and birds tend to
> recover the better-remembered caches first.

This means the memory system may not behave as a collection of equally
strong records.

Conceptually:

``` text
Memory A  ██████████
Memory B  ████████
Memory C  █████
Memory D  ██
```

rather than:

``` text
Memory A  █████
Memory B  █████
Memory C  █████
Memory D  █████
```

### Confidence

**Supported as an interpretation of behavioral results, not as a known
neural storage algorithm.**

### Engineering abstraction: memory strength/confidence

A software memory can maintain evidence-based strength:

``` yaml
memory_strength:
  anchor_integrity: 0.92
  retrieval_success: 0.88
  outcome_support: 1.00
  contradiction_penalty: 0.00
```

Do **not** call this a direct implementation of the bird's neural
"confidence"; it is an engineered analogue.

------------------------------------------------------------------------

## 2.8 Cache creation itself may be important for durable encoding

The 1988 radial-maze analogue produced a striking contrast.

Birds remembered visited locations well for several hours but showed
little retention after 24 hours, whereas actual cache-location
experiments had already shown accurate recovery over much longer
intervals.

The authors discuss several explanations, including task differences and
the possibility that the behavior of **creating a cache** could
"imprint" the location differently.

This is not proof of a dedicated cache-writing algorithm, but it is
highly relevant to an AI memory architecture.

### Engineering hypothesis: active episode formation

Do not persist every token or every observation continuously.

Instead, create durable memories around meaningful events:

``` text
task completed
decision made
bug discovered
failed approach
successful fix
architectural rule learned
test failure explained
dependency changed
```

Possible lifecycle:

``` text
Agent interaction
      │
      ▼
working context
      │
      ├── trivial observation ──> discard
      │
      └── salient event
               │
               ▼
          ENCODE EPISODE
               │
               ▼
       attach stable anchors
               │
               ▼
          persistent memory
```

This is a promising design hypothesis derived from the contrast between
tasks, but **the 1988 study does not establish the mechanism**.

------------------------------------------------------------------------

## 2.9 Revisiting an emptied cache does not mean the location was forgotten

This is another place where the earlier discussion needs correction.

Bednekoff & Balda (2014) explicitly note that nutcrackers may revisit
sites whose caches were recovered in an earlier session, and they cite
previous studies showing that birds can retain memory for cache
locations for days or weeks **after the contents have been recovered**.

Therefore, the simple rule:

``` text
memory retrieved once -> lower priority because "already consumed"
```

is **not directly justified** by these papers.

A better distinction is:

``` text
memory of LOCATION
        ≠
memory of CURRENT CONTENT/STATE
```

That is potentially very useful computationally.

### Engineering abstraction: separate identity from state

``` yaml
location_memory:
  anchor: SessionRepository
  persistent: true

episode:
  id: E184
  location: SessionRepository
  status: resolved

current_state:
  last_verified_commit: a81f3c
  validity: needs_recheck
```

The structural location can remain memorable even after the event
associated with it has been "consumed."

This suggests that **memory identity and memory state should be modeled
separately**.

------------------------------------------------------------------------

## 2.10 Memory-guided behavior can coexist with non-memory heuristics

Applegate & Aronov (2022) studied chickadees, not Clark's nutcrackers,
so this section is comparative rather than species-specific.

Their probabilistic modeling found contributions from:

-   spatial biases;
-   proximity to the previous interaction;
-   memory of which sites contained caches;
-   memory of which sites had already been checked.

They also found that the same memory of site content was used
differently depending on context:

``` text
during caching:
occupied site -> avoid

during retrieval:
occupied site -> approach
```

### Engineering abstraction

Retrieval need not be:

``` text
query -> memory -> answer
```

A richer model is:

``` text
task context
    +
structural position
    +
memory
    +
cheap heuristics
    ↓
action
```

For a coding agent, cheap non-memory heuristics might include:

``` text
currently edited files
git diff
compiler errors
failing tests
import graph neighborhood
recent tool outputs
```

Persistent memory should complement these signals rather than replace
them.

------------------------------------------------------------------------

# 3. Candidate computational model

The following is **our proposed model**, not something explicitly
described by the papers.

## 3.1 Cognitive repository map

Represent a repository as a graph:

``` text
G = (V, E)
```

Possible nodes:

``` text
Repository
Package
Module
File
Class
Function
Interface
Route
DatabaseTable
Test
ExternalService
```

Possible edges:

``` text
CONTAINS
IMPORTS
CALLS
IMPLEMENTS
EXTENDS
READS
WRITES
TESTS
DEPENDS_ON
EXPOSES
```

This graph is the computational analogue of the navigable environment.

------------------------------------------------------------------------

## 3.2 Episode representation

``` yaml
episode:
  id: E184
  type: bug_fix

  summary: >
    Refresh token expiration was caused by session persistence,
    not JWT generation.

  anchors:
    - id: AuthModule
      level: structural
    - id: SessionRepository
      level: regional
    - id: SessionRepository.rotateRefreshToken
      level: local
    - id: AuthIntegrationTests
      level: validation

  observations:
    - "Changing JwtService broke three tests."

  decision:
    - "Modify session persistence instead."

  outcome:
    status: success
    tests_passed: true

  provenance:
    commit: a82fc31

  state:
    structurally_valid: true
    contradicted: false
```

------------------------------------------------------------------------

## 3.3 Multi-anchor encoding

Inspired by the multiple-landmark evidence:

``` text
Memory M
  │
  ├── anchor A: AuthModule
  ├── anchor B: SessionRepository
  ├── anchor C: Redis
  └── anchor D: integration tests
```

No single anchor is the canonical identity of the memory.

------------------------------------------------------------------------

## 3.4 Hierarchical anchor stability

Inspired by the structural-cue evidence:

``` text
repository architecture       high stability
        ↓
module / bounded context
        ↓
class / public API
        ↓
function
        ↓
line / local variable         low stability
```

This is a software hypothesis that should be benchmarked.

------------------------------------------------------------------------

## 3.5 Structural drift instead of simple invalidation

After each meaningful Git change:

``` text
old anchors
    ↓
compare against current repository graph
    ↓
┌──────────────────────────────────┐
│ unchanged                        │
│ renamed/moved but identifiable   │
│ partially broken                 │
│ contradicted                     │
│ no longer exists                 │
└──────────────────────────────────┘
    ↓
update memory state
```

Example:

``` yaml
anchor_state:
  AuthModule: valid
  SessionRepository: valid
  rotateRefreshToken: renamed
  AuthIntegrationTests: valid

overall:
  status: partially_drifted
```

The multi-anchor design permits graceful degradation instead of binary
validity.

------------------------------------------------------------------------

# 4. Proposed retrieval algorithm

**This entire section is an engineering proposal. It must not be
presented as "the Clark's nutcracker algorithm."**

Given task `Q` and current repository location `R`:

### Step 1 --- Locate the task in the repository graph

``` text
Q
↓
candidate symbols/modules
↓
current structural region
```

### Step 2 --- Expand a bounded structural neighborhood

``` text
AuthService
├── SessionRepository
├── JwtService
├── Redis
└── AuthTests
```

### Step 3 --- Retrieve episodes anchored to that neighborhood

Not only:

``` text
semantic_similarity(Q, episode)
```

but:

``` text
semantic relevance
+
structural proximity
+
surviving anchor support
+
outcome usefulness
+
current validity
```

### Step 4 --- Reconcile cue disagreement

If semantic search says memory A is relevant but its structural anchors
are mostly invalid, lower its confidence.

If several independent structural anchors support memory B, preserve it
even if one local symbol was renamed.

### Step 5 --- Return compact context

``` yaml
relevant_memories:
  - summary: "Previous refresh-token bug originated in session persistence."
    why_retrieved:
      - "same module"
      - "same repository dependency"
      - "3/4 anchors still valid"
    status: valid
```

------------------------------------------------------------------------

# 5. Candidate scoring function

A first experimental scoring function could be:

``` text
score(M, Q, R) =

    α * semantic_similarity(M, Q)
  + β * structural_proximity(M, R)
  + γ * anchor_support(M)
  + δ * outcome_utility(M)
  + ε * retrieval_history(M)
  - ζ * structural_drift(M)
  - η * contradiction(M)
```

Important:

-   this equation is **not in the biological literature**;
-   the papers justify investigating multi-cue, structural, persistent
    retrieval;
-   coefficients must be learned/tuned experimentally;
-   temporal age should initially be tested as an optional weak feature
    rather than assumed to dominate.

------------------------------------------------------------------------

# 6. Scientific claims matrix

  -----------------------------------------------------------------------
  Claim                   Evidence level from     Use in Nutcracker
                          uploaded set            
  ----------------------- ----------------------- -----------------------
  Clark's nutcrackers use Strong                  Spatial/structural
  spatial memory to                               memory architecture
  recover caches                                  

  Cache retrieval is not  Strong                  Store relationships,
  simply detection of the                         not just content
  seed                                            

  Landmarks influence     Strong                  Anchor memories to
  cache recovery                                  repository landmarks

  Multiple landmarks can  Strong                  Multi-anchor redundancy
  protect accuracy when                           
  another cue is                                  
  unreliable                                      

  Distance/direction      Supported hypothesis    Relational graph
  relationships are part                          encoding
  of the                                          
  multiple-bearings                               
  hypothesis                                      

  Large/stable            Strong/moderate         Prefer stable
  environmental structure                         architectural anchors
  can matter                                      

  Fine substrate detail   Contradicted            Avoid dependence on
  is always necessary                             line-level identity

  Memory remains above    Strong                  Long-lived persistence
  chance after 285 days                           

  There is zero temporal  Contradicted            Do not claim perfect
  forgetting                                      permanence

  Some memories/caches    Supported               Per-memory
  may be stronger than    interpretation          strength/confidence
  others                                          

  Cache creation may      Plausible, unresolved   Event-driven episodic
  engage a special                                encoding
  durable encoding                                
  process                                         

  Revisiting an emptied   Unsupported             Separate location
  cache proves forgetting                         memory from content
                                                  state

  Chickadees remember     Strong for chickadees   Comparative inspiration
  checked-site state and  only                    for state/context
  use memory contextually                         

  The exact               False                   Nutcracker is
  neural/computational                            bio-inspired, not a
  algorithm is known                              biological reproduction
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 7. What we should NOT claim in the project README or paper

Avoid:

> "Nutcracker implements the memory algorithm used by Clark's
> nutcrackers."

There is no complete known algorithm in these sources.

Prefer:

> "Nutcracker explores a computational memory architecture inspired by
> experimentally observed properties of spatial memory in Clark's
> nutcrackers, including multi-landmark encoding, reliance on stable
> structural cues, long-term persistence, and flexible cue use."

Avoid:

> "Clark's nutcrackers never forget cache locations."

Prefer:

> "Cache-location memory can persist for many months; laboratory
> performance remained above chance after 285 days, although evidence of
> forgetting appeared at the longest interval."

Avoid:

> "Nutcrackers use large landmarks and ignore local ones."

Prefer:

> "Nutcrackers can use local objects as landmarks, while evidence also
> indicates reliance on broader, stable structural cues."

Avoid:

> "Multiple bearings is proven to be the neural representation."

Prefer:

> "The multiple bearings hypothesis provides a formal behavioral account
> in which cache locations are encoded relative to multiple landmarks
> using distance and directional information."

Avoid:

> "Applegate & Aronov demonstrated this mechanism in Clark's
> nutcrackers."

Prefer:

> "Applegate & Aronov demonstrated flexible mnemonic and non-mnemonic
> strategies in black-capped chickadees, providing comparative evidence
> from another food-caching bird."

------------------------------------------------------------------------

# 8. Research hypotheses for the software project

These are **new computational hypotheses** motivated by the biological
literature.

### H1 --- Multi-anchor encoding

Memories attached to multiple structural anchors will survive repository
refactors better than memories attached to a single symbol/path.

### H2 --- Structural retrieval

Combining graph proximity with semantic similarity will retrieve more
task-relevant historical context than vector similarity alone.

### H3 --- Stable-landmark weighting

Weighting architecture-level anchors more strongly than volatile
line/function details will reduce stale-memory failures after
refactoring.

### H4 --- Event-driven encoding

Persisting memories at salient task events will produce a better
signal/noise ratio than storing every conversational turn.

### H5 --- Structural drift

Validity based on actual changes to memory anchors will outperform a
simple time-to-live policy.

### H6 --- Cue redundancy

When one anchor becomes invalid, memories supported by several surviving
anchors will remain useful more often than single-anchor memories.

### H7 --- Location/state separation

Separating persistent structural identity from mutable episode state
will reduce incorrect deletion or suppression of historically useful
memories.

------------------------------------------------------------------------

# 9. Minimum viable experiment

The scientific idea should be tested against simpler baselines.

``` text
A. Codex without persistent memory

B. Codex + semantic/vector memory

C. Codex + code knowledge graph

D. Codex + Nutcracker
   semantic retrieval
   + structural map
   + multi-anchor episodes
   + structural drift
```

Run a sequence of related tasks over the same repository.

Measure:

``` text
task success rate
repeated-error rate
relevant-memory recall
irrelevant-memory retrieval
stale-memory usage
tokens consumed
files inspected
tool calls
time to completion
```

The key research question is not:

> "Does this resemble a bird?"

It is:

> **Do the computational principles motivated by the bird literature
> improve long-horizon agent memory compared with simpler retrieval
> systems?**

------------------------------------------------------------------------

# 10. Design decisions supported by the current source set

For the first prototype:

``` text
YES
✓ persistent episodic memory
✓ repository graph / cognitive map
✓ multiple anchors per memory
✓ hierarchy of structural landmarks
✓ structural-neighborhood retrieval
✓ explicit memory state
✓ Git-based structural drift
✓ semantic retrieval as one cue among several
✓ event-driven memory creation

NOT YET JUSTIFIED
✗ aggressive TTL deletion
✗ automatic decay solely because time passed
✗ deleting/suppressing a memory after first retrieval
✗ treating every code symbol as equally stable
✗ claiming an exact reconstruction of avian memory
✗ claiming a known neural algorithm
```

------------------------------------------------------------------------

# 11. Open questions the uploaded papers do not resolve

The source set does **not** tell us:

1.  the exact neural code for each cache location;
2.  how thousands of cache representations are physically separated in
    memory;
3.  the precise weighting rule when landmarks disagree;
4.  whether distance and direction are represented explicitly by
    particular neural populations in Clark's nutcrackers;
5.  how memories are consolidated at the neural level;
6.  an exact mathematical forgetting function;
7.  how landmark identity itself is recognized across months;
8.  the complete role of the hippocampus in encoding vs. retrieval;
9.  whether a graph is the correct computational analogue;
10. whether these mechanisms improve LLM agent performance.

These should remain research questions rather than assumptions.

------------------------------------------------------------------------

# 12. Additional papers suggested by the uploaded references

The current PDFs repeatedly point to several papers that would
materially improve the knowledge base:

1.  **Kamil & Jones (1997)** --- *Clark's nutcrackers learn geometric
    relationships among landmarks.* Nature 390, 276--279.\
    Important for geometric relational encoding.

2.  **Kamil & Cheng (2001)** --- source of the **multiple bearings
    hypothesis**.\
    Important because the 2019 paper tests predictions derived from this
    model.

3.  **Gould-Beierle & Kamil (1996)** --- *The use of local and global
    cues by Clark's nutcracker.*\
    Important for hierarchical/local-vs-global representation.

4.  **Kamil, Balda, Olson & Good (1993)** --- *Returns to emptied cache
    sites by Clark's nutcrackers: a puzzle revisited.*\
    Important for separating memory of location from current cache
    state.

5.  **Kelly, Kamil & Cheng (2010)** --- landmark use, disorientation,
    cue rotation, distance and direction estimates.\
    Important for understanding how spatial components interact.

6.  **Kamil & Balda (1985)** --- *Cache recovery and spatial memory in
    Clark's nutcrackers.*\
    A foundational cache-recovery study.

These should be added before making strong claims about the final
computational architecture.

------------------------------------------------------------------------

# 13. Compact machine-readable principles

This section is deliberately concise so an AI agent can retrieve the
core scientific constraints without rereading the entire document.

``` yaml
scientific_constraints:

  - id: spatial_memory
    species: clarks_nutcracker
    evidence: strong
    claim: >
      Cache recovery depends substantially on memory for spatial location
      and cannot be reduced to cues emitted by the cached seed.

  - id: landmark_use
    species: clarks_nutcracker
    evidence: strong
    claim: >
      Environmental landmarks influence cache-location encoding and retrieval.

  - id: multiple_cues
    species: clarks_nutcracker
    evidence: strong
    claim: >
      Nutcrackers can use multiple landmarks and other spatial information
      flexibly; multiple landmarks can preserve search accuracy when sun-compass
      information is experimentally made unreliable.

  - id: multiple_bearings
    species: clarks_nutcracker
    evidence: supported_hypothesis
    claim: >
      The multiple bearings hypothesis proposes encoding bearings containing
      distance and directional information from a cache to multiple landmarks.

  - id: structural_cues
    species: clarks_nutcracker
    evidence: strong_moderate
    claim: >
      Broad, stable structural features can be important for accurate cache
      recovery; merely increasing the number of arbitrary floor objects does
      not necessarily improve accuracy.

  - id: long_term_retention
    species: clarks_nutcracker
    evidence: strong
    claim: >
      Cache-location memory remains above chance after retention intervals
      as long as 285 days.

  - id: forgetting
    species: clarks_nutcracker
    evidence: strong
    claim: >
      The evidence does not support zero forgetting. Performance at 285 days
      showed signs consistent with forgetting relative to shorter intervals.

  - id: unequal_memory_strength
    species: clarks_nutcracker
    evidence: supported_interpretation
    claim: >
      Behavioral recovery order is consistent with some cache locations being
      remembered better than others.

  - id: cache_encoding_specialization
    species: clarks_nutcracker
    evidence: unresolved_hypothesis
    claim: >
      Contrasts between cache recovery and radial-maze-like tasks leave open
      the possibility that the act of caching recruits a different or stronger
      encoding process.

  - id: flexible_memory_use
    species: black_capped_chickadee
    evidence: strong_but_comparative
    claim: >
      Chickadees combine memory-guided and non-memory strategies and can use
      memory of site contents differently depending on behavioral context.
```

------------------------------------------------------------------------

# 14. One-sentence architecture derived from the evidence

> **Nutcracker should be tested as a persistent episodic memory system
> in which experiences are redundantly anchored to multiple,
> hierarchically stable regions of a changing structural map, retrieved
> through a combination of semantic and structural cues, and revalidated
> against environmental change rather than discarded by a simplistic
> timer.**

This sentence is an **engineering synthesis** of the evidence, not a
description of a known biological algorithm.

------------------------------------------------------------------------

# References

Balda, R. P., & Kamil, A. C. (1988). *The spatial memory of Clark's
nutcrackers (Nucifraga columbiana) in an analogue of the radial arm
maze*. Animal Learning & Behavior, 16(2), 116--122.

Balda, R. P., & Kamil, A. C. (1992). *Long-term spatial memory in
Clark's nutcracker, Nucifraga columbiana*. Animal Behaviour, 44,
761--769. DOI: 10.1016/S0003-3472(05)80302-1.

Bednekoff, P. A., & Balda, R. P. (2014). *Clark's nutcracker spatial
memory: The importance of large, structural cues*. Behavioural
Processes, 102, 12--17. DOI: 10.1016/j.beproc.2013.12.004.

Kelly, D. M., Cheng, K., Balda, R., & Kamil, A. C. (2019). *Effects of
sun compass error on spatial search by Clark's nutcrackers*. Integrative
Zoology, 14, 172--181. DOI: 10.1111/1749-4877.12302.

Applegate, M. C., & Aronov, D. (2022). *Flexible use of memory by
food-caching birds*. eLife, 10, e70600. DOI: 10.7554/eLife.70600.
