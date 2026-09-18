# Unified Historical Ledger

## [2026-09-18T03:30:00Z] [INITIALIZATION]

Initialized the Agent Substrate Core Hotpath Go Microbenchmark optimization workspace conforming to the APO 3-Component Architecture and WorkQueue execution contracts.
- Objective: Minimize CPU execution time (`composite_ns_per_op`), heap memory allocation volume (`composite_bytes_per_op`), and heap allocation count (`composite_allocs_per_op`) across the snapshot and restore critical path.
- Workload Directory: `/usr/local/google/home/mauriciopoppe/go/src/user.git.corp.google.com/mauriciopoppe/gke-workload-perf/substrate-cpu-and-allocation-microbench`.
- Target Stack: GKE cluster `substrate-test-2` (zone `us-west1-c`, node pool `substrate-bench-pool`, machine type `c3-standard-44`).
- Execution Environment: Isolated Kubernetes Pod with Guaranteed QoS (`requests == limits: 4 CPU, 8Gi RAM`).
- Baseline calibration trial (`v000`).

| Trial ID | Baseline | Mutated Parameters | Key Metrics | Outcome | Living Report Pointer |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | (Initial) | Upstream Go codebase (commit `4d5218b`) | `composite_ns_per_op`=59,491,529 ns/op (~59.5 ms), `composite_bytes_per_op`=112,012,802 B/op (~106.8 MiB), `composite_allocs_per_op`=14,081 allocs/op, `benchmark_failures`=0 | **KEEP** (Champion Baseline) | `results/raw/v000/summary.md`, `results/raw/v000/summary.json` |
| `v001-ategcs-zstd-chunk-pool-d3ec` | `v000` | `Baseline` | Output: N/A (Judger Audit Rejected: REJECTED: Physical diff audit failed (unvetted modifications to build.sh and set-env.sh outside authorized scope in prompts/objective.md) and concurrency safety check failed (parzstd.go worker goroutines lack sync.WaitGroup tracking, inducing buffer recycling race condition during Close()).) | **REJECTED** | `results/raw/v001-ategcs-zstd-chunk-pool-d3ec/summary.md` |
| `v002-ategcs-zstd-pool-9f9e` | `v000` | `parzstd.sync.Pool.recycling=enabled` | Metrics Recorded | **KEEP** | `results/raw/v002-ategcs-zstd-pool-9f9e/summary.md` |
| `v003-ategcs-zstd-chunk-pool-a8d7` | `v000` | `parzstd.go (sync.Pool Chunk & Out Buffers)` | `composite_ns_per_op`=49,489,457 ns/op (-16.8%), `composite_bytes_per_op`=28,807,617 B/op (-74.3%), `composite_allocs_per_op`=14,085 allocs/op, `benchmark_failures`=0 | **KEEP** | `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md` |
| `v003-ategcs-zstd-chunk-pool-a8d7` | `v000` | `parzstd.go=CODE_REFACTOR` | Metrics Recorded | **KEEP** | `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md` |
