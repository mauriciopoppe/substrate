---
trial_id: "v018"
hypothesis_id: "v018-ategcs-a6ad"
parent_trial_id: "v017-ategcs-9228"
status: "COMPLETED"
outcome: "KEEP"
strategy: "EXPLORE"
---

# Trial Summary: v018-ategcs-a6ad

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: v000, v003, v007, v015, v017
- **Active Search Space**: Substrate Subsystems (`ch`, `ategcs`, `tarutil`) pure Go source code.
- **Sensitivity & Trajectory**: Recent trials (`v015`, `v017`) successfully demonstrated extreme heap allocation sensitivity to `sync.Pool` Struct/Arena Recycling and direct interface bypass. E.g. `v017` eliminated 5.15 MiB of allocation churn per `BenchmarkReadSparseZstd` op (-79.5% composite volume) by pooling `zstd.Decoder`.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: From v017 Champion:
  - `BenchmarkWriteSparseZstd`: 22,182,926 B/op (largest heap contributor), 177 allocs/op, 11.46 ms CPU Latency.
- **SLA Status**: MET (0 benchmark failures)
- **Subsystem Health Triage**: Subsystem A (`ategcs`) `writeSparseZstd` path is heavily bottlenecked by Go allocation/GC overhead from `zstd.NewWriter` initializing massive context arrays per pipeline worker, and `io.CopyN` inner buffers creating 32KB arrays per extent. 

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v017-ategcs-9228/summary.md`, `results/raw/v015-tarutil-75c2/summary.md`
- **Subsystem Health Matrix Evidence**: `v017` explicitly isolates `BenchmarkWriteSparseZstd` as the new global limit: "Investigate writer extent buffer pooling and parallel chunk compression allocation reduction."
- **Spanner KB Citations**: N/A (Internal Codebase Benchmark)
- **Domain Memory Recipes**: Go allocator/GC saturation (sync.Pool recycling).
- **Refuted Patterns Avoided**: Does NOT blindly use global static encoders that would induce data races across concurrent `zstd` chunk encoders. Uses `sync.Pool` for thread safety.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Not applicable (no parametric bounds to sample).
- **Option B (Explore Path - Archetype Action)**: `[ACTION: CODE_REFACTOR]` applying Archetype "Zero-allocation buffer reuse" and "Direct slice passing". Extending `v017`'s successful decoder pooling to the writer pipeline, addressing the largest volume contributor directly.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: CODE_REFACTOR
- **Hypothesis ID**: v018-ategcs-a6ad
- **Subsystem Focus**: `substrate/cmd/atelet/internal/ategcs` (Subsystem A)
- **Proposed Mutation Payload**: 
```json
[
  {
    "filename": "substrate/cmd/atelet/internal/ategcs/parzstd.go",
    "intent": "Extract zstd.NewWriter from the worker goroutine into a package-level sync.Pool (zstdEncoderPool) to recycle encoder structs and their internal buffers across invocations, eliminating massive heap allocations per snapshot upload.",
    "target_symbols": [
      "worker",
      "zstdEncoderPool"
    ]
  },
  {
    "filename": "substrate/cmd/atelet/internal/ategcs/sparsezstd.go",
    "intent": "Replace per-extent io.CopyN and binary.Write interface boxing with a pooled 32KB copy buffer (sparseWriteCopyBufPool), a re-used io.LimitedReader, and manual binary.LittleEndian.PutUint64 array packing to eliminate per-extent slice and struct allocations.",
    "target_symbols": [
      "writeSparseZstd",
      "sparseWriteCopyBufPool"
    ]
  }
]
```
- **Expected Gain & Technical Rationale**:
  - `zstd.NewWriter` triggers extensive internal dynamic slice allocations for matching blocks and window management. Moving these behind a `sync.Pool` enables encoder struct re-use across parallel upload workers within and across chunk jobs.
  - Replacing `io.CopyN` with `io.CopyBuffer` + `LimitedReader` re-uses the 32KiB block copy array instead of `make([]byte, 32*1024)` alloc on every extent, drastically slashing the `177 allocs/op`.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated zero-allocation sync.Pool recycling for zstd.Encoder in parzstd.go and pooled 32KB extent buffer with manual binary packing in writeSparseZstd, eliminating heap allocation churn on the critical snapshot upload path.

### 2. Safety Rubric & Checklist Grading
- **Physical Diff Audit**: PASS (Surgical Go modifications strictly within allowed file scope substrate/cmd/atelet/internal/ategcs/)
- **Deduplication Check**: PASS (Unique parameter configuration and novel encoder/copy pool implementation)
- **Domain Trait Check**: PASS (Conforms to apo-provider-go-compiler zero-allocation and sync.Pool safety invariants with private worker encoder usage and sync.WaitGroup lifecycle tracking)
- **Management Cores Check**: PASS (Microbenchmark execution preserves container CPU quota with no management core starvation)
- **Memory Headroom Check**: PASS (Significantly reduces heap allocation bandwidth and GC churn)
- **Layer Isolation Check**: PASS (S_Substrate / ategcs subsystem only)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `FEATURE_ZSTD_ENCODER_POOL_AND_ZERO_ALLOC_EXTENTS` | `true` | `substrate/cmd/atelet/internal/ategcs/parzstd.go` | `apo-provider-go-compiler` |

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | Composite CPU Latency (ns/op) | Composite Heap Volume (B/op) | Composite Heap Allocs (allocs/op) | SLA Status | Outcome / Delta vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 59,491,529 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | Baseline Reference |
| `v017-ategcs-9228` | `sparsezstd.go (zstdDecoderPool Decoder Recycling)` | 47,416,250 ns/op | 22,959,102 B/op | 14,066 allocs/op | PASS | KEEP (-20.3% CPU ns, -79.5% Heap bytes vs Baseline) |
| `v018-ategcs-a6ad` | `parzstd.go (zstdEncoderPool) & sparsezstd.go (sparseWriteCopyBufPool & manual binary packing)` | 47,034,705 ns/op | 16,059,505 B/op | 13,191 allocs/op | PASS | **KEEP (-20.9% CPU ns, -85.7% Heap bytes vs Baseline; -30.1% Heap bytes vs Champion v017)** |

### Subsystem Telemetry & Dynamic Trait Evidence

#### Primary Measured Performance Metrics
- Composite CPU Execution Time (`composite_ns_per_op`): 47,034,705 ns/op (~47.03 ms/op, Median of 3 iterations: iter_1=47,034,705, iter_2=47,757,231, iter_3=46,174,056; Delta vs Baseline: -20.94%, Delta vs Champion v017: -0.80%)
- Composite Heap Allocation Volume (`composite_bytes_per_op`): 16,059,505 B/op (~15.31 MiB/op, Median: 16,059,505, Min: 13,268,004; Delta vs Baseline: -85.66% [-95,953,297 B/op / -91.51 MiB/op], Delta vs Champion v017: -30.05% [-6,899,597 B/op / -6.58 MiB/op])
- Composite Heap Object Allocations (`composite_allocs_per_op`): 13,191 allocs/op (Median: 13,191, Min: 13,183; Delta vs Baseline: -6.32% [-890 allocs], Delta vs Champion v017: -6.22% [-875 allocs])
- Subsystem A Hotpath Breakdown (`cmd/atelet/internal/ategcs`):
  - `BenchmarkWriteSparseZstd`:
    - CPU Latency: 10,014,629 ns/op (vs 11,458,730 ns/op in v017, -12.60% [-1.44 ms/op])
    - Heap Memory: 14,157,214 B/op (vs 22,182,926 B/op in v017, -36.18% [-8,025,712 B / -7.65 MiB heap memory eliminated per write operation])
    - Heap Allocations: 95 allocs/op (vs 177 allocs/op in v017, -46.33% [-82 allocs/op eliminated])
  - `BenchmarkReadSparseZstd`:
    - CPU Latency: 16,491,986 ns/op
    - Heap Memory: 1,214,625 B/op
    - Heap Allocations: 25 allocs/op
- Other Microbenchmark Hotpaths:
  - `BenchmarkMergeDeltaIntoBase`: 2,128,248 ns/op, 2,448 B/op, 27 allocs/op
  - `BenchmarkCopySparseRegions`: 7,673,389 ns/op, 208 B/op, 1 alloc/op
  - `BenchmarkExtract`: 7,158,730 ns/op, 364,062 B/op, 9,141 allocs/op
  - `BenchmarkCreate`: 3,567,723 ns/op, 320,948 B/op, 3,902 allocs/op
- Failures & Errors: 0 (`benchmark_failures`: 0, Error Rate: 0.0%)
- SLA Compliance: YES (All constraints met; `benchmark_failures` == 0)

#### Dynamic Trait Evidence

##### Trait Evidence: apo-provider-go-compiler

###### sync.Pool zstd.Encoder Arena Recycling in parzstd.go
- Pattern Implementation: Applied Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling) to `substrate/cmd/atelet/internal/ategcs/parzstd.go`.
- Encoder Recycling: Extracted per-worker calls to `zstd.NewWriter` into a package-level pointer-backed pool `zstdEncoderPool`. Each worker goroutine acquires an encoder from the pool and resets it with its output buffer destination via `enc.Reset(buf)`.
- Concurrency & Lifecycle Invariant: Dedicated encoder instances are operated strictly within private worker goroutines and returned via `defer zstdEncoderPool.Put(enc)` upon worker completion, accompanied by `sync.WaitGroup` worker tracking to prevent race conditions during pipeline teardown.

###### Zero-Allocation Extent Buffer Pooling & Manual Binary Packing in sparsezstd.go
- Extent Buffer Recycling: Replaced per-extent `io.CopyN` slice allocation with a pooled 32KB extent buffer (`sparseWriteCopyBufPool`) and `io.CopyBuffer` utilizing a reusable `io.LimitedReader`.
- Manual Binary Packing: Replaced interface-boxing `binary.Write` calls with fixed-array `binary.LittleEndian.PutUint64` serialization, eliminating heap escapes on extent metadata serialization.
- Subsystem Allocation Impact: Slashed `BenchmarkWriteSparseZstd` heap volume from 22.18 MiB/op to 14.16 MiB/op (-36.18%) and cut allocation counts nearly in half from 177 to 95 allocs/op (-46.33%). Combined with v017 decoder recycling, overall suite heap volume dropped to 15.31 MiB/op (-85.66% vs Baseline v000).

### Summary & Recommendations
- **Outcome**: KEEP (Strict Pareto domination over champion `v017-ategcs-9228`: -30.05% heap allocation volume [-6.58 MiB/op], -0.80% composite CPU runtime, -875 allocs/op, with 0 benchmark failures).
- **Modified Files**:
  - `substrate/cmd/atelet/internal/ategcs/parzstd.go` (zstdEncoderPool for recycling zstd.Encoder across workers)
  - `substrate/cmd/atelet/internal/ategcs/sparsezstd.go` (sparseWriteCopyBufPool 32KB buffer pool, re-used io.LimitedReader, and manual binary packing for extent header writing)
- **Recommendations for Next Cycle**:
  1. Subsystem C (`substrate/internal/tarutil`): `BenchmarkExtract` currently accounts for 9,141 allocs/op (69.3% of total suite allocations) and 7.16 ms CPU time, while `BenchmarkCreate` accounts for 3,902 allocs/op (29.6% of allocations). Follow up on zero-allocation tar header extraction, stat caching, and pool recycling in `tarutil.go`.
  2. Subsystem A (`substrate/cmd/atelet/internal/ategcs`): `BenchmarkWriteSparseZstd` remains 14.16 MiB/op, where `fastBase.ensureHist` and `writeSparseSourceTB` contribute significant memory. Investigate pre-allocating zstd history windows and chunk buffer recycling.
  3. Subsystem B (`substrate/cmd/ateom-microvm/internal/ch`): `BenchmarkCopySparseRegions` CPU latency is 7.67 ms/op with 66.7% time in `Syscall6` (`unix.Seek`). Investigate batching `SEEK_DATA`/`SEEK_HOLE` scans or chunked multi-block copy buffers.

