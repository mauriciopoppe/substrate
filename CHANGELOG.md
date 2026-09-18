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
