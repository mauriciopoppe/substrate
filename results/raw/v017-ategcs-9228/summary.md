---
trial_id: "v017"
hypothesis_id: "v017-ategcs-9228"
parent_trial_id: "v007-ch-sparse-buf-pool-3cb6"
status: "COMPLETED"
outcome: "KEEP"
strategy: "EXPLORE"
---

# Trial Summary: v017-ategcs-9228

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: `v007-ch-sparse-buf-pool-3cb6` and `v003-ategcs-zstd-chunk-pool-a8d7` (Outcome: KEEP / Champion Baselines)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized across `substrate/internal/tarutil/`, `substrate/cmd/ateom-microvm/internal/ch/`, and `substrate/cmd/atelet/internal/ategcs/`.
- **Sensitivity & Trajectory**: Trials `v011` through `v015` completed the search within Subsystem C (`tarutil`). Per the rotation directives in `prompts/objective.md`, following saturation of primary gains in Subsystem C, the Generator MUST pivot back to Subsystem A (`ategcs`), executing the mandatory sequence `ategcs` -> `ch` -> `tarutil` -> `ategcs`.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: N/A (Based on champion baseline `v007` metrics proxying current state)
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0 in prior trials)
- **Subsystem Health Triage**:
  - In Subsystem A (`substrate/cmd/atelet/internal/ategcs`), `BenchmarkReadSparseZstd` contributes 16.65 ms CPU time (34.3% of composite latency) and 5.53 MiB heap volume. 
  - Over half of the allocation overhead inside `readSparseZstd` occurs from repeatedly initializing new `zstd.Decoder` readers via `zstd.NewReader`, allocating buffers internally without reuse across operations.
- **Active Trait Providers Loaded**: 
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`, `results/raw/v007-ch-sparse-buf-pool-3cb6/summary.md`, `results/raw/v015-tarutil-75c2/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `ategcs.BenchmarkReadSparseZstd`: 16.65 ms CPU time and 5.53 MiB heap volume (from `v007` Summary).
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace, existing registered `campaign_id` 8e2d67b7-024d-4ed2-be54-e5853355d92a).
- **Domain Memory Recipes**: Reusable `sync.Pool` buffer arenas with safe reuse.
- **Refuted Patterns Avoided**:
  - Maintained logical chunk boundaries and `zstd` decoder resets before utilization to avoid data corruption between snapshot restorations.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling. Refuted due to lack of environment-tunable variables in the benchmark test scope.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`. Replaces naive local `zstd.NewReader` creation in `readSparseZstd` with a package-level pointer-backed `sync.Pool` (`zstdDecoderPool`) coupled with `dec.Reset(src)`, caching the pre-allocated ~5.5 MiB internal structures to dramatically drop heap allocation volume inside Subsystem A.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v017-ategcs-9228`
- **Subsystem Focus**: `substrate/cmd/atelet/internal/ategcs` (Subsystem A)
- **Proposed Mutation Payload**: `{"files": [{"filename": "substrate/cmd/atelet/internal/ategcs/sparsezstd.go", "status": "modified", "patch": "..."}]}` (See CLI payload)
- **Expected Gain & Technical Rationale**:
  - Uses a package level `sync.Pool` for reusing the `zstd.Decoder` structs.
  - Bypasses repeated dynamic buffer allocation inside `zstd.NewReader` entirely. This should heavily sink the 5.5 MiB/op heap allocations, cutting total composite allocations and potentially trimming the 16.65 ms CPU time inside `readSparseZstd`.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/cmd/atelet/internal/ategcs/sparsezstd.go`. Replaces per-invocation `zstd.NewReader` allocation in `readSparseZstd` with a package-level `sync.Pool` (`zstdDecoderPool`) and `zr.Reset(src)`, safely recycling pre-allocated internal zstd decoder tables and buffers across snapshot restoration cycles while preserving thread safety and stream integrity.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique mutation targeting `readSparseZstd` decoder pooling in Subsystem A `ategcs`, distinct from previous chunk/output buffer pooling in `parzstd.go`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `substrate/cmd/atelet/internal/ategcs/sparsezstd.go`; matches `INPUT_MUTATED_SPEC` 1:1; no unauthorized scripts or files modified)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Conforms to Pattern 2 buffer/struct arena recycling; zero goroutine leaks; zero unprotected mutable global state; clean decoder reset on reuse)
- **Management Cores Check**: PASS (Node management infrastructure unmutated; microbenchmark pod runs with Guaranteed QoS)
- **Memory Headroom & OOM Guard**: PASS (Eliminates repeated ~5.5 MiB heap allocations per decompression operation, reducing memory churn and GC mark worker overhead)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem A `cmd/atelet/internal/ategcs`)
- **Infrastructure Mutation Check**: PASS (No nodepool, machine type, or cluster resource alterations)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `sparsezstd.go (zstdDecoderPool)` | `CODE_REFACTOR` | `substrate/cmd/atelet/internal/ategcs/sparsezstd.go` | `apo-provider-go-compiler` |

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | Composite CPU Latency (ns/op) | Composite Heap Volume (B/op) | Composite Heap Allocs (allocs/op) | SLA Status | Outcome / Delta vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 59,491,529 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | Baseline Reference |
| `v007-ch-sparse-buf-pool-3cb6` | `ch/merge.go (sparseCopyBufPool 1MiB Buffer Recycling)` | 48,569,843 ns/op | 26,561,940 B/op | 14,080 allocs/op | PASS | **KEEP (-18.4% CPU ns, -76.3% Heap bytes vs Baseline)** |
| `v017-ategcs-9228` | `sparsezstd.go (zstdDecoderPool Decoder Recycling)` | 47,416,250 ns/op | 22,959,102 B/op | 14,066 allocs/op | PASS | **KEEP (-20.3% CPU ns, -79.5% Heap bytes vs Baseline; -13.6% Heap bytes vs Champion)** |

### Subsystem Telemetry & Dynamic Trait Evidence

#### Primary Measured Performance Metrics
- Composite CPU Execution Time (`composite_ns_per_op`): 47,416,250 ns/op (~47.42 ms/op, Median of 3 iterations: iter_1=47,800,820, iter_2=47,416,250, iter_3=46,795,169, Delta vs Baseline: -20.30%, Delta vs Champion v007: -2.37%)
- Composite Heap Allocation Volume (`composite_bytes_per_op`): 22,959,102 B/op (~21.90 MiB/op, Median: 22,959,102, Min: 22,959,102, Delta vs Baseline: -79.50% [-89.05 MiB/op], Delta vs Champion v007: -13.56% [-3.44 MiB/op / -3,602,838 B/op])
- Composite Heap Object Allocations (`composite_allocs_per_op`): 14,066 allocs/op (Median: 14,066, Delta vs Baseline: -0.11% [-15 allocs], Delta vs Champion v007: -0.10% [-14 allocs])
- Subsystem A Hotpath Breakdown (`cmd/atelet/internal/ategcs/sparsezstd.go`):
  - `BenchmarkReadSparseZstd`:
    - CPU Latency: 15,712,618 ns/op (vs 16,653,901 ns/op in v007, -5.65%)
    - Heap Memory: 131,619 B/op (vs 5,531,892 B/op in v007, -97.62% [-5,400,273 B / ~5.15 MiB heap memory eliminated per decompression operation!])
    - Heap Allocations: 20 allocs/op (vs 37 allocs/op in v007, -45.95% [-17 allocs])
  - `BenchmarkWriteSparseZstd`: 11,458,730 ns/op, 22,182,926 B/op, 177 allocs/op
- Other Microbenchmark Hotpaths:
  - `BenchmarkMergeDeltaIntoBase`: 2,093,223 ns/op, 2,448 B/op, 27 allocs/op
  - `BenchmarkCopySparseRegions`: 7,198,219 ns/op, 208 B/op, 1 alloc/op
  - `BenchmarkExtract`: 7,161,468 ns/op, 396,649 B/op, 9,542 allocs/op
  - `BenchmarkCreate`: 3,791,992 ns/op, 245,252 B/op, 4,299 allocs/op
- Failures & Errors: 0 (`benchmark_failures`: 0, Error Rate: 0.0%)
- SLA Compliance: YES (All constraints met; `benchmark_failures` == 0)

#### Dynamic Trait Evidence

##### Trait Evidence: apo-provider-go-compiler

###### sync.Pool zstd.Decoder Arena Recycling in Subsystem A
- Pattern Implementation: Applied Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling) to `substrate/cmd/atelet/internal/ategcs/sparsezstd.go`.
- Memory Elimination: Replaced per-invocation allocations in `readSparseZstd` (`zstd.NewReader(src, zstd.WithDecoderConcurrency(1))`) with a package-level pointer-backed pool `zstdDecoderPool`.
- Heap Volume Impact: `BenchmarkReadSparseZstd` heap volume plummeted from 5,531,892 B/op (~5.28 MiB) in v007 to 131,619 B/op (~128 KiB), eliminating over 5.15 MiB of allocation churn per call (-97.62% reduction). Composite suite allocation volume dropped from 26.56 MiB/op to 21.90 MiB/op (-13.56% vs Champion v007; -79.50% vs Baseline v000).
- CPU Latency Impact: Eliminating GC allocation pressure and repeated zstd table initialization during sparse read streaming reduced `BenchmarkReadSparseZstd` CPU time from 16.65 ms/op to 15.71 ms/op (-5.65%), reducing overall composite CPU time to 47.42 ms/op (-2.37% vs Champion v007; -20.30% vs Baseline v000).

###### Concurrency Safety & Decoder Reset Sanitization
- Proper Reset Protocol: Retrieved `zstd.Decoder` from `zstdDecoderPool.Get().(*zstd.Decoder)` and re-initialized streaming state via `zr.Reset(src)` before reading, preventing cross-operation stream corruption.
- Deterministic Reclaim: Reclaimed decoder instance deterministically via `defer zstdDecoderPool.Put(zr)`, ensuring no pool leakage across concurrent decompression operations.

### Summary & Recommendations
- **Outcome**: KEEP (Strict Pareto domination over champion `v007-ch-sparse-buf-pool-3cb6`: -13.56% heap allocation volume [-3.44 MiB/op], -2.37% composite CPU runtime, -14 allocs/op, with 0 benchmark failures).
- **Recommendations for Next Cycle**:
  1. Subsystem C (`substrate/internal/tarutil`): `BenchmarkExtract` currently accounts for 9,542 allocs/op (~67.8% of all suite allocations) and 7.16 ms CPU time. Follow up on `v015` zero-allocation header extraction and interface boxing reduction in `tarutil.go`.
  2. Subsystem A (`substrate/cmd/atelet/internal/ategcs`): `BenchmarkWriteSparseZstd` remains the largest single heap contributor at 22.18 MiB/op and 11.46 ms CPU time. Investigate writer extent buffer pooling and parallel chunk compression allocation reduction.
