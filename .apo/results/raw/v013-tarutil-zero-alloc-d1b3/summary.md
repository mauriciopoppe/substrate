---
trial_id: "v013"
hypothesis_id: "v013-tarutil-zero-alloc-d1b3"
parent_trial_id: "v007-ch-sparse-buf-pool-3cb6"
status: "EXECUTED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v013-tarutil-zero-alloc-d1b3

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v007-ch-sparse-buf-pool-3cb6`: `composite_ns_per_op` = 48,569,843 ns/op (-18.4%), `composite_bytes_per_op` = 26,561,940 B/op (-76.3%), `composite_allocs_per_op` = 14,080 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP / Champion Baseline)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/cmd/ateom-microvm/internal/ch/`, `substrate/cmd/atelet/internal/ategcs/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Trials `v004` through `v007` explored Subsystem B (`ch`), which saturated gains in `ch/merge.go` buffer allocations. Per rotation directives in `prompts/objective.md`, following saturation of primary gains in `ch`, the search pivots to Subsystem C (`tarutil`), which is currently in state `UNEXPLORED`.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 48,569,843 ns/op
  - `composite_bytes_per_op`: 26,561,940 B/op
  - `composite_allocs_per_op`: 14,080 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - In Subsystem C (`substrate/internal/tarutil`), `BenchmarkExtract` currently accounts for 9,541 allocs/op (67.8% of all suite allocations) and 7.33 ms CPU time per `v007`'s Living report.
  - Allocations in Subsystem C are dominated by `os.splitPathInRoot` via standard library methods, strings allocation returning from Header extract (e.g. `strings.Split`, map creations), and `copyPooled()` interface boxing overhead.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling), Judger Concurrency & Safety Rubric.

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v007-ch-sparse-buf-pool-3cb6/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `tarutil.BenchmarkExtract`: 7,325,752 ns/op, 381,872 B/op, 9,541 allocs/op.
  - Profiling reveals `copyPooled` allocating roughly 1,820 heap objects per benchmark loop due to interface parameter boxing when constructing `writerOnly` and `readerOnly` structures. `readOverlayXattrs` allocates strings and maps on every call during extraction.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` for pointer-backed interface wrapper injection, Zero-allocation header extraction using `bytes` package processing instead of `strings`.
- **Refuted Patterns Avoided**:
  - Refrained from touching unvetted shell scripts or infrastructure configurations, keeping mutations strictly isolated to authorized source code in `tarutil`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling. Refuted because this Go microbenchmark workspace has no external tunable environment variables.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]` targeting `substrate/internal/tarutil/tarutil.go`. Implements zero-allocation header extraction optimizations (`restoreOverlayXattrs`, `readOverlayXattrs`) and avoids interface parameter boxing in `copyPooled` by pooling a custom `copyWrapper` struct.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v013-tarutil-zero-alloc-d1b3`
- **Subsystem Focus**: `substrate/internal/tarutil` (Rootfs Archive Streaming)
- **Proposed Mutation Payload**: payload attached in orchestrator queue registration.
- **Expected Gain & Technical Rationale**:
  - Eliminates the repeated 2-allocation interface boxing penalty in `copyPooled` via `copyWrapperPool`.
  - Replaces heavy string allocations with direct byte processing where available during `readOverlayXattrs`.
  - Replaces `fmt.Sprintf` with zero-allocation `strconv.Itoa` during `restoreOverlayXattrs` resolving.
  - Overall expect up to 400 allocation drop (-4% in composite) for `BenchmarkExtract` per operation.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated against Go performance engineering guidelines and concurrency safety rubrics. Refactor safely pools `copyWrapper` pointer structures with explicit pointer reset before `sync.Pool.Put`, eliminates intermediate heap map allocations in `restoreOverlayXattrs`, and reduces heap churn in `readOverlayXattrs` via `bytes.Split` and `bytes.HasPrefix`.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique refactor combining copyWrapper pooling and zero-allocation xattr handling)
- **Management Cores Check**: PASS (Node management infrastructure unmutated; pure Go microbenchmark workspace)
- **Memory Headroom Check**: PASS (Reduces heap allocations across extraction hotpaths)
- **Layer & Subsystem Isolation Check**: PASS (S_Substrate / tarutil runtime component only)
- **Domain Trait Guardrails**: PASS (Preserves sync.Pool cleanup invariants, context cancellation safety, and error handling)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `tarutil.go (zero-alloc xattrs & copyWrapper pool)` | `CODE_REFACTOR` | `substrate/internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |
