# Substrate Hotpath Go Microbenchmark Baseline

## Target Workload
- **Environment**: Linux x86_64 (`Intel(R) Xeon(R) CPU @ 2.20GHz`, 24 cores)
- **Scope**: Pure Go hotpaths across snapshot merging, sparse extent zstd compression/decompression, and rootfs upper tar operations.
- **Suite**: 3 iterations, median trial selected based on `composite_ns_per_op`.

## Baseline Summary Metrics (Median: Iteration 2)

| Metric | Baseline Value | Optimization Goal |
| :--- | :--- | :--- |
| **`composite_ns_per_op`** | **237,785,523 ns/op (~237.8 ms)** | Minimize (CPU latency across all 6 hotpaths) |
| **`composite_bytes_per_op`** | **330,094,515 B/op (~314.8 MiB)** | Minimize (Heap bytes allocated per operation) |
| **`composite_allocs_per_op`** | **14,600 allocs/op** | Minimize (Heap allocations per operation) |
| **`benchmark_failures`** | **0** | Constraint (<= 0) |

## Per-Benchmark Breakdown

| Benchmark | Latency (`ns/op`) | Memory Allocated (`B/op`) | Allocations (`allocs/op`) |
| :--- | :--- | :--- | :--- |
| `BenchmarkMergeDeltaIntoBase` | 6,233,513 ns/op (6.2 ms) | 1,051,027 B/op (~1 MiB) | 28 allocs/op |
| `BenchmarkCopySparseRegions` | 22,024,543 ns/op (22.0 ms) | 1,048,784 B/op (~1 MiB) | 2 allocs/op |
| `BenchmarkWriteSparseZstd` | 63,243,523 ns/op (63.2 ms) | 321,778,875 B/op (~306.9 MiB) | 249 allocs/op |
| `BenchmarkReadSparseZstd` | 44,037,795 ns/op (44.0 ms) | 5,538,888 B/op (~5.3 MiB) | 40 allocs/op |
| `BenchmarkExtract` | 80,819,685 ns/op (80.8 ms) | 356,673 B/op (~348 KiB) | 9,540 allocs/op |
| `BenchmarkCreate` | 21,426,284 ns/op (21.4 ms) | 320,268 B/op (~312 KiB) | 4,741 allocs/op |

## Identified Optimization Opportunities
1. **`BenchmarkWriteSparseZstd`**: Allocating ~307 MiB per operation due to unpooled zstd encoders and extent buffers.
2. **`BenchmarkCopySparseRegions`**: Allocating a fresh 1 MiB chunk buffer on every call; can use `sync.Pool` or in-kernel `copy_file_range(2)`.
3. **`BenchmarkExtract`**: High allocation count (9,540 allocs/op) from path string manipulations and metadata lookups.
