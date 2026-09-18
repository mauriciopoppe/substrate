---
trial_id: "v014"
hypothesis_id: "v014-tarutil-zero-alloc-a8ea"
parent_trial_id: "v007-ch-sparse-buf-pool-3cb6"
status: "VALIDATED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v014-tarutil-zero-alloc-a8ea

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
  - Profiling reveals `copyPooled` allocating heap objects due to interface parameter boxing when constructing `writerOnly` and `readerOnly` structures. `readOverlayXattrs` allocates strings and maps on every call during extraction. `restoreOverlayXattrs` allocates maps and triggers `fmt.Sprintf` dynamically.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling), Judger Concurrency & Safety Rubric.

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v007-ch-sparse-buf-pool-3cb6/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `tarutil.BenchmarkExtract`: 7,325,752 ns/op, 381,872 B/op, 9,541 allocs/op.
  - Profiling on Baseline/`v007` indicates `copyPooled` causing boxing GC pressure, and `archive/tar` header xattr parsing incurring heavy heap bounds.
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
- **Hypothesis ID**: `v014-tarutil-zero-alloc-a8ea`
- **Subsystem Focus**: `substrate/internal/tarutil` (Rootfs Archive Streaming)
- **Proposed Mutation Payload**: Payload provided in orchestrator queue registration.
- **Expected Gain & Technical Rationale**:
  - Eliminates the repeated 2-allocation interface boxing penalty in `copyPooled` via `copyWrapperPool`.
  - Replaces heavy string allocations with direct byte processing via `bytes` chunking in `readOverlayXattrs`.
  - Replaces `fmt.Sprintf` with zero-allocation `strconv.Itoa` string concat during `restoreOverlayXattrs` resolving.
  - Down-scales `BenchmarkExtract` alloc overhead significantly contributing to composite latency.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/internal/tarutil/tarutil.go`. Replaces per-call interface boxing in `copyPooled` with a pooled `copyWrapper` struct (`copyWrapperPool`) with deterministic sanitization/reset before pooling, eliminates unnecessary map and string formatting allocations in `restoreOverlayXattrs`, and converts string-based tokenization to byte slice processing (`bytes.Split`) in `readOverlayXattrs`. Preserves thread safety and data integrity while reducing heap allocations on the archive extraction critical path.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code refactor exploring Subsystem C `tarutil`, building upon champion `v007-ch-sparse-buf-pool-3cb6`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `substrate/internal/tarutil/tarutil.go`; no unauthorized scripts or config modified)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe `sync.Pool` usage with field clearing, zero goroutine leaks, zero unprotected mutable global state)
- **Management Cores Check**: PASS (Microbenchmark pod runs with Guaranteed QoS; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (Heap allocations reduced across hotpath extraction and copy functions)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem C `tarutil`)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `tarutil.go (copyWrapperPool, zero-alloc xattr)` | `CODE_REFACTOR` | `substrate/internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |
