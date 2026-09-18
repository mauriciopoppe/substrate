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
| `v014-tarutil-zero-alloc-a8ea` | `v007-ch-sparse-buf-pool-3cb6` | `tarutil.go (copyWrapperPool, zero-alloc xattr)=CODE_REFACTOR` | Metrics Recorded | **KEEP** | `results/raw/v014-tarutil-zero-alloc-a8ea/summary.md` |
| `v016-tarutil-bcb4` | `v007-ch-sparse-buf-pool-3cb6` | `Baseline` | Output: N/A (Judger Audit Rejected: REJECTED: Fast-path mode resolution directly from os.FileMode(hdr.Mode) in restoredMode strips POSIX setuid, setgid, and sticky bits, silently dropping directory/file permissions and violating data integrity constraints in prompts/objective.md.) | **REJECTED** | `results/raw/v016-tarutil-bcb4/summary.md` |
| `v017-ategcs-9228` | `v007-ch-sparse-buf-pool-3cb6` | `sparsezstd.go (zstdDecoderPool)=CODE_REFACTOR` | Metrics Recorded | **KEEP** | `results/raw/v017-ategcs-9228/summary.md` |
| `v015-tarutil-75c2` | `v007-ch-sparse-buf-pool-3cb6` | `tarutil.go (copyStatePool & FileInfo bypass)=CODE_REFACTOR` | `composite_ns_per_op`=49,230,299 ns/op (-17.2%), `composite_bytes_per_op`=26,671,934 B/op (-76.2%), `composite_allocs_per_op`=13,283 allocs/op (-5.7%), `benchmark_failures`=0 | **KEEP** | `results/raw/v015-tarutil-75c2/summary.md` |

| `v019-build_flags-9d13` | `v017-ategcs-9228` | `OPTIMIZE_PARKING_ATOMIC=true` | Output: N/A (Judger Audit Rejected: REJECTED: Physical diff modifies code outside authorized scope in prompts/objective.md (cmd/atenet/internal/router/ingress/parking.go is not part of hotpaths ch, ategcs, tarutil), violates concurrency semantics (replaces sync.Once with uncoordinated atomic.Bool return), and diverges from generator proposal (build.sh).) | **REJECTED** | `results/raw/v019-build_flags-9d13/summary.md` |
| `v023-tarutil-be4a` | `v017-ategcs-9228` | `FEATURE_TARUTIL_ZERO_ALLOC=true` | Output: N/A (Judger Audit Rejected: REJECTED: Deduplication and safety check failed: duplicates refuted pattern from trial v016-tarutil-bcb4; fast-path mode resolution directly from os.FileMode(hdr.Mode) in restoredMode strips POSIX setuid, setgid, and sticky bits (04000/02000/01000 in hdr.Mode do not map to os.FileMode bits 23/22/20), silently dropping directory/file permissions upon extraction and violating data integrity constraints in prompts/objective.md.) | **REJECTED** | `results/raw/v023-tarutil-be4a/summary.md` |
| `v034-ch-b639` | `v024-tarutil-mega-768e` | `Baseline` | Output: N/A (Judger Audit Rejected: REJECTED: Duplicate parameter vector and refactoring pattern matching active proposal v029-ch-00e0, and I/O error-handling safety failure in copySparseRegions (infinite loop on io.EOF).) | **REJECTED** | `results/raw/v034-ch-b639/summary.md` |
