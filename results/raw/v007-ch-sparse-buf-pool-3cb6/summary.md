---
trial_id: "v007"
hypothesis_id: "v007-ch-sparse-buf-pool-3cb6"
parent_trial_id: "v003-ategcs-zstd-chunk-pool-a8d7"
status: "COMPLETED"
outcome: "KEEP"
strategy: "EXPLORE"
---

# Trial Summary: v007-ch-sparse-buf-pool-3cb6

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v003-ategcs-zstd-chunk-pool-a8d7`: `composite_ns_per_op` = 49,489,457 ns/op (-16.8%), `composite_bytes_per_op` = 28,807,617 B/op (-74.3%), `composite_allocs_per_op` = 14,085 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP / Champion Baseline)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/cmd/ateom-microvm/internal/ch/`, `substrate/cmd/atelet/internal/ategcs/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Trials `v001` through `v003` explored Subsystem A (`ategcs`), achieving a massive 74.3% reduction in heap allocation volume via `parzstd.go` buffer pooling. Per rotation directives in `prompts/objective.md`, following saturation of primary gains in `ategcs`, the search pivots to Subsystem B (`ch`), which is currently in state `UNEXPLORED`.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 49,489,457 ns/op
  - `composite_bytes_per_op`: 28,807,617 B/op (~27.5 MiB)
  - `composite_allocs_per_op`: 14,085 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - In Subsystem B (`cmd/ateom-microvm/internal/ch/merge.go`), `BenchmarkMergeDeltaIntoBase` (2,528,923 ns/op, 1,051,024 B/op) and `BenchmarkCopySparseRegions` (7,728,751 ns/op, 1,048,784 B/op) together contribute over 2.09 MiB/op of heap allocation volume and ~10.25 ms of CPU execution time.
  - Inspection of `copySparseRegions()` reveals that on every invocation, a fresh 1 MiB (`1<<20`) byte slice is allocated on the heap via `make([]byte, 1<<20)`. This buffer is used purely as scratch space for streaming data regions between file descriptors and is immediately discarded when copying completes.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling), Judger Concurrency & Safety Rubric.

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `ch.BenchmarkMergeDeltaIntoBase`: 2,528,923 ns/op, 1,051,024 B/op (~1 MiB/op).
  - `ch.BenchmarkCopySparseRegions`: 7,728,751 ns/op, 1,048,784 B/op (~1 MiB/op).
  - Both microbenchmarks call `copySparseRegions()`, which allocates 1 MiB per invocation.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` buffer arenas with safe pointer reuse.
- **Refuted Patterns Avoided**:
  - Refrained from touching unvetted shell scripts or infrastructure configurations (`build.sh`, `set-env.sh`), keeping mutations strictly isolated to authorized source code.
  - Avoided slice capacity corruption or retaining large references by recycling fixed-size 1 MiB chunk buffers through a dedicated package-level `sync.Pool`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling. Refuted because this Go microbenchmark workspace has no external tunable environment variables.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]` targeting `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Introduces package-level `sparseCopyBufPool` (`sync.Pool`) for the 1 MiB scratch buffer in `copySparseRegions()`, eliminating 2.09 MiB of heap churn per operation across sparse overlay merging and kernel sparse region copying.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v007-ch-sparse-buf-pool-3cb6`
- **Subsystem Focus**: `cmd/ateom-microvm/internal/ch` (Sparse Memory Overlay Merging & Kernel Region Copying)
- **Proposed Mutation Payload**:
  ```json
  [
    {
      "filename": "substrate/cmd/ateom-microvm/internal/ch/merge.go",
      "status": "modified",
      "patch": "--- a/substrate/cmd/ateom-microvm/internal/ch/merge.go\n+++ b/substrate/cmd/ateom-microvm/internal/ch/merge.go\n@@ -24,9 +24,19 @@\n \t\"io\"\n \t\"os\"\n \t\"os/exec\"\n+\t\"sync\"\n \n \t\"github.com/agent-substrate/substrate/cmd/ateom-microvm/internal/reaper\"\n \t\"golang.org/x/sys/unix\"\n )\n \n+const sparseChunkSize = 1 << 20\n+\n+var sparseCopyBufPool = sync.Pool{\n+\tNew: func() any {\n+\t\tb := make([]byte, sparseChunkSize)\n+\t\treturn &b\n+\t},\n+}\n+\n // MergeSparseOverlay reconstructs a COMPLETE memory snapshot from an OnDemand\n@@ -181,7 +191,9 @@\n \t}\n \tsize := si.Size()\n \tsfd := int(src.Fd())\n-\tbuf := make([]byte, 1<<20)\n+\tbp := sparseCopyBufPool.Get().(*[]byte)\n+\tdefer sparseCopyBufPool.Put(bp)\n+\tbuf := *bp\n \toff := int64(0)\n \tfor off < size {\n"
    }
  ]
  ```
- **Expected Gain & Technical Rationale**:
  - Eliminates the repeated 1 MiB heap buffer allocation on every invocation of `copySparseRegions()`.
  - Decreases composite heap allocation volume (`composite_bytes_per_op`) by ~2.09 MiB/op (~7.3% reduction on top of `v003`) and reduces GC pressure in `runtime.mallocgc` during sparse overlay merges.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Reuses 1 MiB scratch copy buffers via package-level `sync.Pool` (`sparseCopyBufPool`) with deterministic `defer Put(bp)`, eliminating ~2.09 MiB of heap allocations per iteration across sparse overlay merging and kernel sparse region copying hotpaths while preserving data integrity and thread safety.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique mutation building on top of Champion `v003-ategcs-zstd-chunk-pool-a8d7`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `substrate/cmd/ateom-microvm/internal/ch/merge.go`; no unauthorized scripts or config modified)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe `sync.Pool` usage, slice buffer capacity preserved, zero goroutine leaks, zero unprotected mutable global state)
- **Management Cores Check**: PASS (Microbenchmark pod runs with Guaranteed QoS; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (1 MiB heap allocation eliminated per call, reducing GC mark worker CPU overhead)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem B `cmd/ateom-microvm/internal/ch`)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `ch/merge.go (sparseCopyBufPool)` | `CODE_REFACTOR` | `substrate/cmd/ateom-microvm/internal/ch/merge.go` | `apo-provider-go-compiler` |

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | Composite CPU Latency (ns/op) | Composite Heap Volume (B/op) | Composite Heap Allocs (allocs/op) | SLA Status | Outcome / Delta vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 59,491,529 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | Baseline Reference |
| `v003-ategcs-zstd-chunk-pool-a8d7` | `parzstd.go (sync.Pool Chunk & Out Buffers)` | 49,489,457 ns/op | 28,807,617 B/op | 14,085 allocs/op | PASS | **KEEP (-16.8% CPU ns, -74.3% Heap bytes)** |
| `v007-ch-sparse-buf-pool-3cb6` | `ch/merge.go (sparseCopyBufPool 1MiB Buffer Recycling)` | 48,569,843 ns/op | 26,561,940 B/op | 14,080 allocs/op | PASS | **KEEP (-18.4% CPU ns, -76.3% Heap bytes vs Baseline; -7.8% Heap bytes vs Champion)** |

### Subsystem Telemetry & Dynamic Trait Evidence

#### Primary Measured Performance Metrics
- Composite CPU Execution Time (`composite_ns_per_op`): 48,569,843 ns/op (~48.57 ms/op, Median of 3 iterations: iter_1=48,803,610, iter_2=47,656,100, iter_3=48,569,843, Delta vs Baseline: -18.36%, Delta vs Champion v003: -1.86%)
- Composite Heap Allocation Volume (`composite_bytes_per_op`): 26,561,940 B/op (~25.33 MiB/op, Median: 26,561,940, Min: 26,561,940, Delta vs Baseline: -76.29% [-85.45 MiB/op], Delta vs Champion v003: -7.80% [-2.25 MiB/op / -2,245,677 B/op])
- Composite Heap Object Allocations (`composite_allocs_per_op`): 14,080 allocs/op (Median: 14,080, Delta vs Baseline: -0.007%, Delta vs Champion v003: -0.035%)
- Subsystem B Hotpath Breakdown (`cmd/ateom-microvm/internal/ch/merge.go`):
  - `BenchmarkMergeDeltaIntoBase`:
    - CPU Latency: 2,108,617 ns/op (vs 2,528,923 ns/op in v003 / baseline, -16.62%)
    - Heap Memory: 2,448 B/op (vs 1,051,024 B/op in v003 / baseline, -99.77% [-1,048,576 B / exactly 1 MiB scratch allocation eliminated!])
    - Heap Allocations: 27 allocs/op (vs 28 allocs/op in v003 / baseline, -1 alloc)
  - `BenchmarkCopySparseRegions`:
    - CPU Latency: 7,472,374 ns/op (vs 7,728,751 ns/op in v003 / baseline, -3.32%)
    - Heap Memory: 208 B/op (vs 1,048,784 B/op in v003 / baseline, -99.98% [-1,048,576 B / exactly 1 MiB scratch allocation eliminated!])
    - Heap Allocations: 1 alloc/op (vs 2 allocs/op in v003 / baseline, -1 alloc)
- Other Microbenchmark Hotpaths:
  - `BenchmarkWriteSparseZstd`: 11,586,596 ns/op, 20,400,268 B/op, 175 allocs/op
  - `BenchmarkReadSparseZstd`: 16,653,901 ns/op, 5,531,892 B/op, 37 allocs/op
  - `BenchmarkExtract`: 7,325,752 ns/op, 381,872 B/op, 9,541 allocs/op
  - `BenchmarkCreate`: 3,422,603 ns/op, 245,252 B/op, 4,299 allocs/op
- Failures & Errors: 0 (`benchmark_failures`: 0, Error Rate: 0.0%)
- SLA Compliance: YES (All constraints met; `benchmark_failures` == 0)

#### Dynamic Trait Evidence

##### Trait Evidence: apo-provider-go-compiler

###### sync.Pool 1MiB Scratch Buffer Recycling in Subsystem B
- Pattern Implementation: Applied Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling) to `substrate/cmd/ateom-microvm/internal/ch/merge.go`.
- Memory Elimination: Replaced fresh heap allocations (`make([]byte, 1<<20)`) in `copySparseRegions()` with a package-level pointer-backed pool `sparseCopyBufPool`.
- Heap Volume Impact: Both `BenchmarkMergeDeltaIntoBase` (2.4 KiB vs 1.05 MiB) and `BenchmarkCopySparseRegions` (208 B vs 1.05 MiB) had their 1 MiB heap allocations eliminated per iteration, reducing composite heap allocation volume by 2.25 MiB/op (-7.80% reduction relative to champion `v003`).
- CPU Latency Impact: Eliminating GC allocation pressure during sparse region copying reduced CPU execution time in `BenchmarkMergeDeltaIntoBase` by 16.62% and `BenchmarkCopySparseRegions` by 3.32%, bringing composite latency down to 48.57 ms/op.

###### Pointer-backed sync.Pool Safety & Scope Hygiene
- Clean Slice Retention: Used pointer to byte slice (`*[]byte`) in `sparseCopyBufPool` to prevent pool interface boxing allocations during `Get()` and `Put()`.
- Scope Isolation: Reclaimed buffer deterministically via `defer sparseCopyBufPool.Put(bp)` within the localized scope of `copySparseRegions()`, guaranteeing no memory leaks or cross-goroutine pool corruption.

### Summary & Recommendations
- **Outcome**: KEEP (Strict Pareto domination over champion `v003-ategcs-zstd-chunk-pool-a8d7`: -7.80% heap allocation volume [-2.25 MiB/op], -1.86% composite CPU runtime, with 0 benchmark failures).
- **Recommendations for Next Cycle**:
  1. Subsystem C (`substrate/internal/tarutil`): `BenchmarkExtract` currently accounts for 9,541 allocs/op (67.8% of all suite allocations) and 7.33 ms CPU time. Explore zero-allocation header extraction and pooled tar reader buffers in `tarutil.go`.
  2. Subsystem A (`substrate/cmd/atelet/internal/ategcs`): `BenchmarkReadSparseZstd` contributes 16.65 ms CPU time (34.3% of composite latency) and 5.53 MiB heap volume. Explore streaming decompression chunk pooling in `sparsezstd.go`.
