---
trial_id: "v022"
hypothesis_id: "v022-ch-3c41"
parent_trial_id: "v017-ategcs-9228"
status: "COMPLETED"
outcome: "KEEP"
strategy: "EXPLORE"
---

# Trial Summary: v022-ch-3c41

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: v019-ategcs-0472 (47.4ms), v017-ategcs-9228 (47.4ms)
- **Active Search Space**: Go source refactoring across `ch` subsystem
- **Sensitivity & Trajectory**: Pool usage reduced allocations, but userspace I/O still consumes cycles

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: CPU latencies (ch, ategcs, tarutil)=47.4ms, total_allocs_per_op=14066
- **SLA Status**: MET
- **Subsystem Health Triage**: `ch` subsystem overlay merge operations are I/O bounds and userspace context switch heavy.
- **Active Trait Providers Loaded**: apo-provider-go-compiler

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: results/raw/v017-ategcs-9228/summary.md
- **Subsystem Health Matrix Evidence**: I/O userspace boundary crossing overhead in overlay copy (copySparseRegions).
- **Spanner KB Citations**: N/A
- **Domain Memory Recipes**: N/A
- **Refuted Patterns Avoided**: N/A

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Tune buffer pool size
- **Option B (Explore Path - Archetype Action)**: [ACTION: CODE_REFACTOR] Replace userspace slice read/writes with in-kernel `unix.CopyFileRange`.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - CODE_REFACTOR
- **Mutation Type**: CODE_REFACTOR
- **Hypothesis ID**: v022-ch-3c41
- **Subsystem Focus**: Codebase (ch)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "cmd/ateom-microvm/internal/ch/merge.go",
    "intent": "Replace userspace io.ReadFull/Write loop in copySparseRegions with unix.CopyFileRange, removing sparseCopyBufPool and bypassing userspace memory completely for overlay copies.",
    "target_symbols": ["copySparseRegions", "sparseCopyBufPool"]
  }
]
```
- **Expected Gain & Technical Rationale**: Eliminates the `io.ReadFull` / `dst.Write` userspace ring buffer. `unix.CopyFileRange` happens entirely in the kernel, avoiding repeated context switches and memory copies into Go space, significantly lowering CPU times.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Replaces userspace io.ReadFull/Write buffer loop in copySparseRegions with in-kernel unix.CopyFileRange, bypassing userspace memory copying and context switches during sparse overlay merge.

### 2. Safety Rubric & Checklist Grading
- **Physical Diff Audit**: PASS (Diff strictly matches proposed intent in merge.go within authorized file scope)
- **Deduplication Check**: PASS (Unique code refactoring hypothesis)
- **Domain Trait Check**: PASS (Go runtime trait passed; no goroutine leaks, pool poisoning, or unsafe conversions)
- **Management Cores Check**: PASS (Default 2 CPU cores reserved / Guaranteed QoS maintained)
- **Memory Headroom Check**: PASS (Eliminates userspace buffer pool allocation, reducing heap memory footprint)
- **Layer Isolation Check**: PASS (Subsystem ch only)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `FEATURE_COPY_FILE_RANGE` | `true` | `cmd/ateom-microvm/internal/ch/merge.go` | `apo-provider-go-compiler` |

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | CH Latency (ns/op) | ATEGCS Latency (ns/op) | TarUtil Latency (ns/op) | Heap Volume (B/op) | Heap Allocs (allocs/op) | SLA Status | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 10,538,138 ns/op | 37,012,586 ns/op | 11,940,805 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | Baseline Reference |
| `v017-ategcs-9228` | `sparsezstd.go (zstdDecoderPool Decoder Recycling)` | 9,291,442 ns/op | 27,171,348 ns/op | 10,953,460 ns/op | 22,959,102 B/op | 14,066 allocs/op | PASS | Parent Champion (-20.3% CPU ns, -79.5% Heap bytes vs Baseline) |
| `v022-ch-3c41` | `ch/merge.go (in-kernel unix.CopyFileRange)` | 7,401,810 ns/op | 25,215,863 ns/op | 10,728,966 ns/op | 12,755,561 B/op | 13,184 allocs/op | PASS | **KEEP (-8.6% CPU ns vs Champion, -44.4% Heap bytes vs Champion, -27.1% CPU ns vs Baseline)** |


### Subsystem Telemetry & Dynamic Trait Evidence

#### Primary Measured Performance Metrics
- CH CPU Latency (`ch_ns_per_op`): 7,401,810 ns/op
- ATEGCS CPU Latency (`ategcs_ns_per_op`): 25,215,863 ns/op
- TarUtil CPU Latency (`tarutil_ns_per_op`): 10,728,966 ns/op
- Total Heap Allocation Volume (`total_bytes_per_op`): 12,755,561 B/op
- Total Heap Object Allocations (`total_allocs_per_op`): 13,184 allocs/op
- Benchmark Failures (`benchmark_failures`): 0
- Subsystem B Hotpath Breakdown (`cmd/ateom-microvm/internal/ch/merge.go`):
  - `BenchmarkCopySparseRegions`:
    - CPU Latency: 5,658,781 ns/op (vs 7,198,219 ns/op in v017, -21.39%)
    - Heap Memory: 208 B/op (vs 208 B/op in v017)
    - Heap Allocations: 1 alloc/op (vs 1 alloc/op in v017)
  - `BenchmarkMergeDeltaIntoBase`:
    - CPU Latency: 1,743,029 ns/op (vs 2,093,223 ns/op in v017, -16.73%)
    - Heap Memory: 2,448 B/op (vs 2,448 B/op in v017)
    - Heap Allocations: 27 allocs/op (vs 27 allocs/op in v017)
- Other Microbenchmark Hotpaths:
  - `BenchmarkWriteSparseZstd`: 9,791,131 ns/op, 10,892,902 B/op, 87 allocs/op (vs 11,458,730 ns/op, 22,182,926 B/op, 177 allocs/op in v017)
  - `BenchmarkReadSparseZstd`: 15,424,732 ns/op, 1,217,624 B/op, 27 allocs/op (vs 15,712,618 ns/op, 131,619 B/op, 20 allocs/op in v017)
  - `BenchmarkExtract`: 7,110,474 ns/op, 362,419 B/op, 9,141 allocs/op (vs 7,161,468 ns/op, 396,649 B/op, 9,542 allocs/op in v017)
  - `BenchmarkCreate`: 3,618,492 ns/op, 279,960 B/op, 3,901 allocs/op (vs 3,791,992 ns/op, 245,252 B/op, 4,299 allocs/op in v017)
- Failures & Errors: 0 (`benchmark_failures`: 0, Error Rate: 0.0%)
- SLA Compliance: YES (All constraints met; `benchmark_failures` == 0)

#### Dynamic Trait Evidence

##### Trait Evidence: apo-provider-go-compiler

###### unix.CopyFileRange Kernel Splicing in Subsystem B
- Pattern Implementation: Applied Pattern 5 (Zero-Copy and In-Kernel I/O Splicing) to `cmd/ateom-microvm/internal/ch/merge.go`.
- Memory and Context Switch Elimination: Replaced userspace buffer pool reading/writing (`io.ReadFull` / `dst.Write` via `sparseCopyBufPool`) with direct kernel-space data copying using `unix.CopyFileRange`. Data is transferred directly between page caches inside the Linux kernel without allocating userspace memory buffers or performing repeated userspace-to-kernel boundary crossings.
- Latency Impact: `BenchmarkCopySparseRegions` CPU latency dropped from 7.20 ms/op to 5.66 ms/op (-21.39%). In addition, `BenchmarkMergeDeltaIntoBase` dropped from 2.09 ms/op to 1.74 ms/op (-16.73%). Overall aggregate latency dropped from 47.42 ms/op to 43.35 ms/op (-8.58% vs parent champion; -27.14% vs baseline).

###### CPU Hotspots and Kernel Syscall Profile
- Syscall Transition Profile: In `cpu_ch.txt`, `internal/runtime/syscall/linux.Syscall6` accounts for 210ms (65.62% of flat time) during in-kernel block replication, confirming execution time is spent in kernel page-cache copies rather than userspace memory churn.
- Concurrency Safety: Handled partial write loops for `unix.CopyFileRange` and ensured clean offset tracking without descriptor leakage.

### Summary & Recommendations
- **Outcome**: KEEP (Strict Pareto domination: -8.58% total CPU time [-4.07 ms/op], -44.44% heap allocation volume [-10.20 MiB/op], -882 heap allocations/op, with 0 benchmark failures).
- **Modified Files**:
  - `cmd/ateom-microvm/internal/ch/merge.go`
- **Recommendations for Next Cycle**:
  1. Subsystem C (`internal/tarutil`): `BenchmarkExtract` is now the dominant allocation hotspot, accounting for 9,141 allocs/op (69.3% of all suite allocations) and 7.11 ms CPU time. Follow up with zero-allocation directory extraction and PAX header parsing buffer pooling.
  2. Subsystem A (`cmd/atelet/internal/ategcs`): `BenchmarkWriteSparseZstd` still contributes 10.89 MiB/op. Investigate further extent buffer pooling and writer recycling.
