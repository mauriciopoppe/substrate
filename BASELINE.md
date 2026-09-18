# Substrate Hotpath Go Microbenchmark Baseline (GCP C3 Pod)

## Target Workload & Hardware
- **Platform**: GKE cluster `substrate-test-2` (Project `mauriciopoppe-gke-dev`, zone `us-west1-c`)
- **Execution Target**: Dedicated isolated Kubernetes Pod on `c3-standard-44` (`cloud.google.com/gke-nodepool: substrate-bench-pool`)
- **QoS Class**: **Guaranteed** (Requests == Limits: `cpu: 4`, `memory: 8Gi`)
- **Scope**: Pure Go hotpaths across snapshot merging, sparse extent zstd compression/decompression, and rootfs upper tar operations.
- **Suite**: 3 iterations, median trial selected based on `composite_ns_per_op`.

## Baseline Summary Metrics (Median: Iteration 2)

| Metric | Baseline Value | Optimization Goal |
| :--- | :--- | :--- |
| **`composite_ns_per_op`** | **58,009,016 ns/op (~58.0 ms)** | Minimize (CPU latency across all 6 hotpaths) |
| **`composite_bytes_per_op`** | **111,988,491 B/op (~106.8 MiB)** | Minimize (Heap bytes allocated per operation) |
| **`composite_allocs_per_op`** | **14,082 allocs/op** | Minimize (Heap allocations per operation) |
| **`benchmark_failures`** | **0** | Constraint (<= 0) |

## Per-Benchmark Breakdown on C3 Hardware

| Benchmark | Latency (`ns/op`) | Memory Allocated (`B/op`) | Allocations (`allocs/op`) |
| :--- | :--- | :--- | :--- |
| `BenchmarkMergeDeltaIntoBase` | 2,504,043 ns/op (2.5 ms) | 1,051,024 B/op (~1.0 MiB) | 28 allocs/op |
| `BenchmarkCopySparseRegions` | 8,509,979 ns/op (8.5 ms) | 1,048,787 B/op (~1.0 MiB) | 2 allocs/op |
| `BenchmarkWriteSparseZstd` | 18,721,702 ns/op (18.7 ms) | 103,656,238 B/op (~98.8 MiB) | 172 allocs/op |
| `BenchmarkReadSparseZstd` | 17,656,710 ns/op (17.7 ms) | 5,534,833 B/op (~5.3 MiB) | 38 allocs/op |
| `BenchmarkExtract` | 7,163,156 ns/op (7.2 ms) | 370,392 B/op (~361 KiB) | 9,541 allocs/op |
| `BenchmarkCreate` | 3,453,426 ns/op (3.5 ms) | 327,217 B/op (~320 KiB) | 4,301 allocs/op |

## Concurrency & Resource Isolation
- Each trial provisions an ephemeral Pod (`bench-runner-<RUN_ID>`) with a unique run ID, enabling multiple independent APO optimization trials to execute in parallel without port, file, or memory collision.
- The Pod is trapped on `EXIT` so cleanup occurs reliably even upon failure or cancellation.
