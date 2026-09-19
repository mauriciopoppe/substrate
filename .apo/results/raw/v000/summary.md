---
trial_id: "v000"
hypothesis_id: "v000"
parent_trial_id: null
status: "COMPLETED"
outcome: "KEEP"
strategy: "BASELINE"
---

# Trial Summary: v000 (Initial Baseline)

## [GENERATOR_HYPOTHESIS]
- **Target Subsystems**: `cmd/ateom-microvm/internal/ch`, `cmd/atelet/internal/ategcs`, `internal/tarutil`
- **Objective**: Establish the calibrated CPU latency and memory allocation baseline across pure Go microbenchmarks executing inside an isolated Kubernetes Pod on `c3-standard-44` (`substrate-bench-pool`).
- **Proposed Mutation**: Unmodified upstream codebase (commit `4d5218b`).

## [JUDGER_DECISION]
- **Verdict**: APPROVED
- **Rationale**: Initial baseline trial calibrated directly on the target GKE C3 hardware environment.

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | CH Latency (ns/op) | ATEGCS Latency (ns/op) | TarUtil Latency (ns/op) | Heap Volume (B/op) | Heap Allocs (allocs/op) | SLA Status | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 10,538,138 ns/op | 37,012,586 ns/op | 11,940,805 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | **KEEP** (Champion Baseline) |


### Subsystem Telemetry & Dynamic Trait Evidence

#### Primary Measured Performance Metrics
- CH CPU Latency (`ch_ns_per_op`): 10,538,138 ns/op
- ATEGCS CPU Latency (`ategcs_ns_per_op`): 37,012,586 ns/op
- TarUtil CPU Latency (`tarutil_ns_per_op`): 11,940,805 ns/op
- Total Heap Allocation Volume (`total_bytes_per_op`): 112,012,802 B/op
- Total Heap Object Allocations (`total_allocs_per_op`): 14,081 allocs/op
- Benchmark Failures (`benchmark_failures`): 0

#### Detailed Hotpath Breakdown (Median Run: Iteration 3)

| Component | Benchmark | Latency (`ns/op`) | Memory (`B/op`) | Allocations (`allocs/op`) | Hotpath Profile Observations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `ch` | `BenchmarkMergeDeltaIntoBase` | 2,539,025 | 1,051,024 | 28 | Base snapshot rename + dirty page overlay into raw base file |
| `ch` | `BenchmarkCopySparseRegions` | 7,999,113 | 1,048,784 | 2 | `unix.Seek` (`SEEK_DATA`/`SEEK_HOLE`) extent copy loop |
| `ategcs` | `BenchmarkWriteSparseZstd` | 19,098,276 | 103,655,995 | 171 | **Primary memory allocator**: 103.6 MiB/op in parallel chunk zstd writer |
| `ategcs` | `BenchmarkReadSparseZstd` | 17,914,310 | 5,534,833 | 38 | High CPU consumer: 17.9 ms in decompression stream and sparse punch |
| `tarutil` | `BenchmarkExtract` | 8,498,733 | 394,939 | 9,541 | **Primary allocation count hotspot**: 9,541 allocs/op during header & dir extraction |
| `tarutil` | `BenchmarkCreate` | 3,442,072 | 327,227 | 4,301 | Tar header creation, file walk, and xattr read loop |

### Summary & Recommendations
- **Outcome**: **KEEP**  -  Established as the active champion baseline across the Pareto frontier.
- **Top Optimization Vectors for Future Trials**:
  1. `BenchmarkWriteSparseZstd`: Emits 92.5% of total heap bytes (103.6 MiB / 112.0 MiB). Buffer pooling with `sync.Pool` for zstd encoder chunk buffers can dramatically reduce garbage collection pressure.
  2. `BenchmarkExtract`: Emits 67.8% of total allocations (9,541 / 14,081). Reusing path buffers and avoiding per-file header heap escapes will significantly cut alloc counts.
  3. `BenchmarkReadSparseZstd` & `BenchmarkWriteSparseZstd`: Account for ~62% of total CPU latency (37.0 ms / 59.5 ms). Tuning concurrency and dictionary/window parameters will reduce CPU cycles.
