---
trial_id: "v015"
hypothesis_id: "v015-tarutil-75c2"
parent_trial_id: "v007-ch-sparse-buf-pool-3cb6"
status: "COMPLETED"
outcome: "KEEP"
strategy: "EXPLORE"
---

# Trial Summary: v015-tarutil-75c2

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: `v007-ch-sparse-buf-pool-3cb6` and `v003-ategcs-zstd-chunk-pool-a8d7` (Outcome: KEEP / Champion Baselines)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized across `substrate/internal/tarutil/`, `substrate/cmd/ateom-microvm/internal/ch/`, and `substrate/cmd/atelet/internal/ategcs/`.
- **Sensitivity & Trajectory**: Trials `v001` through `v007` explored Subsystem A (`ategcs`) and Subsystem B (`ch`), driving massive reductions in heap allocation volume via `parzstd.go` buffer pooling and `sparseCopyBufPool`. Per rotation directives in `prompts/objective.md` and explicit recommendation in `v007`, the search continues to Subsystem C (`tarutil`).

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: N/A (Based on champion baseline `v007` metrics proxying current state)
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0 in prior trials)
- **Subsystem Health Triage**:
  - In Subsystem C (`substrate/internal/tarutil`), `BenchmarkExtract` currently accounts for over 9,500 allocs/op, representing the majority of the suite's remaining heap object allocations.
  - Inspection of `tarutil.go` reveals two major sources of allocations per file entry: `hdr.FileInfo().Mode()` returning an interface per file, and `copyPooled(dst, src)` boxing value structs into `io.Writer` and `io.Reader` interfaces on each invocation of `io.CopyBuffer`.
- **Active Trait Providers Loaded**: 
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`, `results/raw/v007-ch-sparse-buf-pool-3cb6/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `tarutil.BenchmarkExtract`: 9,541 allocs/op (~67.8% of all suite allocations) and ~7.33 ms CPU time.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` arenas with pointer wrapper semantics to bypass interface boxing allocations.
- **Refuted Patterns Avoided**:
  - Avoiding breaking posix bits mapping by preserving the standard bit layout when deriving the permissions manually from the raw `tar.Header.Mode`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling. Refuted due to lack of environment-tunable variables in the benchmark test scope.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`. Replaces `copyPooled()` dynamic interface wrapping structs with a sync.Pool of pre-allocated `copyState` objects carrying pointer methods. Also fast-paths `hdr.FileInfo().Mode().Perm()` and `restoredMode` directly from `os.FileMode(hdr.Mode)`.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v015-tarutil-75c2`
- **Subsystem Focus**: `substrate/internal/tarutil` (Subsystem C)
- **Proposed Mutation Payload**: `{"files": [{"filename": "substrate/internal/tarutil/tarutil.go", "status": "modified", "patch": "..."}]}` (See CLI payload)
- **Expected Gain & Technical Rationale**:
  - Eliminates value boxing within `copyPooled` by utilizing a pointer method implementation cached in a pool.
  - Bypasses `FileInfo()` allocation overhead for file headers. Expected to drop allocations per operation by several hundreds, significantly alleviating GC overhead.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/internal/tarutil/tarutil.go`. Safely eliminates interface boxing allocations in `copyPooled` by pooling a reusable `copyState` structure (`copyStatePool`) with pointer methods and deterministic reference sanitization before `sync.Pool.Put`. Bypasses `tar.Header.FileInfo()` interface construction overhead in `extractEntry` and `restoredMode` by deriving `os.FileMode` directly from `hdr.Mode` while preserving exact permission, setuid, setgid, and sticky bit semantics.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code refactor targeting copyState pointer pooling and FileInfo mode bypass in Subsystem C `tarutil`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `substrate/internal/tarutil/tarutil.go`; no unauthorized scripts or config modified)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe `sync.Pool` usage with explicit field reset, zero goroutine leaks, zero unprotected mutable global state)
- **Management Cores Check**: PASS (Node management infrastructure unmutated; pure Go microbenchmark workspace running with Guaranteed QoS)
- **Memory Headroom & OOM Guard**: PASS (Reduces heap allocations across archive extraction and copy hotpaths)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem C `tarutil`)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `tarutil.go (copyStatePool & FileInfo bypass)` | `CODE_REFACTOR` | `substrate/internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | Composite CPU Latency (ns/op) | Composite Heap Volume (B/op) | Composite Heap Allocs (allocs/op) | SLA Status | Outcome / Delta vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 59,491,529 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | Baseline Reference |
| `v003-ategcs-zstd-chunk-pool-a8d7` | `parzstd.go (sync.Pool Chunk & Out Buffers)` | 49,489,457 ns/op | 28,807,617 B/op | 14,085 allocs/op | PASS | **KEEP (-16.8% CPU ns, -74.3% Heap bytes)** |
| `v007-ch-sparse-buf-pool-3cb6` | `ch/merge.go (sparseCopyBufPool 1MiB Buffer Recycling)` | 48,569,843 ns/op | 26,561,940 B/op | 14,080 allocs/op | PASS | **KEEP (-18.4% CPU ns, -76.3% Heap bytes vs Baseline; -7.8% Heap bytes vs Champion)** |
| `v015-tarutil-75c2` | `tarutil.go (copyStatePool & FileInfo bypass)` | 49,230,299 ns/op | 26,671,934 B/op | 13,283 allocs/op | PASS | **KEEP (-17.2% CPU ns, -76.2% Heap bytes, -5.7% Allocs vs Baseline; -5.7% Allocs vs Champion)** |

### Subsystem Telemetry & Dynamic Trait Evidence

> [!IMPORTANT]
> **HEADER NESTING LEVEL CONTRACT**:
> - Level 2 (`##`): `## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis`
> - Level 3 (`###`): `### Subsystem Telemetry & Dynamic Trait Evidence`
> - Level 4 (`####`): `#### Primary Measured Performance Metrics` AND `#### Dynamic Trait Evidence`
> - Level 5 (`#####`): `##### Trait Evidence: <trait-name>` (Each active trait provider block MUST be H5 (`#####`))
> - Level 6 (`######`): `###### <subheading-name>` (All profiler/metric subheadings inside a trait block MUST be H6 (`######`))

#### Primary Measured Performance Metrics
- Composite CPU Execution Time (`composite_ns_per_op`): 49,230,299 ns/op (~49.23 ms/op, Median of 3 iterations: iter_1=48,451,351, iter_2=49,385,638, iter_3=49,230,299; Delta vs Baseline v000: -17.25%, Delta vs Parent Champion v007: +1.36% [within 3.0% noise tolerance])
- Composite Heap Allocation Volume (`composite_bytes_per_op`): 26,671,934 B/op (~25.44 MiB/op, Median: 26,671,934, Min: 26,671,934, Max: 32,045,690; Delta vs Baseline v000: -76.19%, Delta vs Parent Champion v007: +0.41% [within 1.0% noise tolerance])
- Composite Heap Object Allocations (`composite_allocs_per_op`): 13,283 allocs/op (Median: 13,283; Delta vs Baseline v000: -5.67% [-798 allocs/op], Delta vs Parent Champion v007: -5.66% [-797 allocs/op])
- Subsystem C Hotpath Breakdown (`internal/tarutil/tarutil.go`):
  - `BenchmarkExtract`:
    - CPU Latency: 7,077,714 ns/op (vs 7,325,752 ns/op in v007, -3.39%)
    - Heap Memory: 390,278 B/op (vs 381,872 B/op in v007)
    - Heap Allocations: 9,142 allocs/op (vs 9,541 allocs/op in v007, -399 allocs/op / -4.18% reduction!)
  - `BenchmarkCreate`:
    - CPU Latency: 3,454,472 ns/op (vs 3,422,603 ns/op in v007)
    - Heap Memory: 238,993 B/op (vs 245,252 B/op in v007, -2.55%)
    - Heap Allocations: 3,899 allocs/op (vs 4,299 allocs/op in v007, -400 allocs/op / -9.30% reduction!)
- Subsystem A & B Microbenchmark Breakdown:
  - `BenchmarkMergeDeltaIntoBase`: 2,104,205 ns/op, 2,448 B/op, 27 allocs/op
  - `BenchmarkCopySparseRegions`: 7,607,625 ns/op, 208 B/op, 1 alloc/op
  - `BenchmarkWriteSparseZstd`: 11,056,007 ns/op, 20,505,171 B/op, 176 allocs/op
  - `BenchmarkReadSparseZstd`: 17,930,276 ns/op, 5,534,836 B/op, 38 allocs/op
- Failures & Errors: 0 (`benchmark_failures`: 0, Error Rate: 0.0%)
- SLA Compliance: YES (All constraints met; `benchmark_failures` == 0)

#### Dynamic Trait Evidence

##### Trait Evidence: apo-provider-go-compiler

###### sync.Pool Pointer CopyState & FileInfo Allocation Bypass in Subsystem C
- Pattern Implementation: Applied Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling) to `substrate/internal/tarutil/tarutil.go`.
- Memory Allocation Elimination:
  - Replaced per-copy dynamic interface wrapping in `copyPooled` with a pooled `copyState` structure carrying pointer methods (`*writerOnly`, `*readerOnly`) and explicit reference reset (`cs.w.Writer = nil`, `cs.r.Reader = nil`) before `copyStatePool.Put(cs)`.
  - Bypassed `hdr.FileInfo()` construction overhead in `extractEntry` and `restoredMode` by deriving `os.FileMode` directly from `hdr.Mode` with bitwise permission mapping (`fs.ModePerm`, `fs.ModeSetuid`, `fs.ModeSetgid`, `fs.ModeSticky`).
- Allocation Count Impact:
  - `BenchmarkExtract` allocations dropped from 9,541 to 9,142 allocs/op (-399 allocs/op).
  - `BenchmarkCreate` allocations dropped from 4,299 to 3,899 allocs/op (-400 allocs/op).
  - Total composite allocations dropped from 14,080 to 13,283 allocs/op (-797 allocs/op / -5.66% reduction), successfully crossing the 5.0% min improvement threshold for objective `composite_allocs_per_op`.
- CPU Latency & Volume Impact:
  - Composite execution time remained steady at 49.23 ms/op (+1.36% vs v007, well within the 3.0% noise tolerance).
  - Composite heap volume remained steady at 26.67 MiB/op (+0.41% vs v007, within the 1.0% noise tolerance).

###### Concurrency Safety & Interface Hygiene
- Reset Safety: `cs.w.Writer = nil` and `cs.r.Reader = nil` are set deterministically before returning `cs` to `copyStatePool`, preventing interface reference leaks across goroutines.
- POSIX Bit Fidelity: Bit masking in `restoredMode` directly preserves `ModeSetuid`, `ModeSetgid`, and `ModeSticky` bits without requiring intermediate `fs.FileInfo` interface boxing.

### Summary & Recommendations
- **Outcome**: KEEP (Strict Pareto promotion: achieves -5.66% reduction in composite heap object allocations [13,283 vs 14,080 allocs/op], eliminating 797 allocations/op on the rootfs packaging critical path while maintaining CPU latency and memory volume within noise tolerances, and 0 benchmark failures).
- **Recommendations for Next Cycle**:
  1. Subsystem C (`substrate/internal/tarutil`): Now that interface boxing and FileInfo allocations are resolved in `tarutil.go`, remaining extract allocations reside in path operations and directory map entries. Consider pre-allocating the `dirs` map with estimated capacity.
  2. Subsystem A (`substrate/cmd/atelet/internal/ategcs`): `BenchmarkReadSparseZstd` contributes 17.93 ms CPU time (36.4% of composite runtime) and 5.53 MiB heap volume. Explore streaming decompression chunk pooling in `sparsezstd.go`.
