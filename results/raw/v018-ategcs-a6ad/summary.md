---
trial_id: "v018"
hypothesis_id: "v018-ategcs-a6ad"
parent_trial_id: "v017-ategcs-9228"
status: "RUNNING"
outcome: "VALIDATED"
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
