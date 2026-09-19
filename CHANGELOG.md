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

| `v019-ategcs-0472` | `v017-ategcs-9228` | `FEATURE_SPARSEZSTD_WRITE_POOL=true` | Metrics Recorded | **KEEP** | `results/raw/v019-ategcs-0472/summary.md` |
| `v021-ch-5866` | `v017-ategcs-9228` | `FEATURE_CH_SPARSE_STAT=true` | Output: N/A (Judger Audit Rejected: Target worktree directory does not exist or was canceled/pruned by QueueManager) | **REJECTED** | `results/raw/v021-ch-5866/summary.md` |
| `v018-ategcs-a6ad` | `v017-ategcs-9228` | `FEATURE_ZSTD_ENCODER_POOL_AND_ZERO_ALLOC_EXTENTS=true` | Metrics Recorded | **KEEP** | `results/raw/v018-ategcs-a6ad/summary.md` |
| `v023-tarutil-1758` | `v019-ategcs-0472` | `FEATURE_COPY_STATE_POOL=true` | Output: N/A (Judger Audit Rejected: REJECTED: Duplicate refactor of trial v015-tarutil-75c2 (commit 2ec6a12) already present on main branch, resulting in empty physical worktree diff.) | **REJECTED** | `results/raw/v023-tarutil-1758/summary.md` |
| `v022-ch-3c41` | `v017-ategcs-9228` | `FEATURE_COPY_FILE_RANGE=true` | Metrics Recorded | **KEEP** | `results/raw/v022-ch-3c41/summary.md` |
| `v026-tarutil-e72b` | `v018-ategcs-a6ad` | `FEATURE_TARUTIL_MAP_AND_STAT_POOLING=true` | Output: N/A (Judger Audit Rejected: Target file not found in workload directory: substrate/internal/tarutil/tarutil.go (worktree does not exist)) | **REJECTED** | `results/raw/v026-tarutil-e72b/summary.md` |
| `v024-tarutil-3a24` | `v019-ategcs-0472` | `FEATURE_TARUTIL_XATTR_POOL=true` | Metrics Recorded | **KEEP** | `results/raw/v024-tarutil-3a24/summary.md` |
| `v028-tarutil-ac8c` | `v022-ch-3c41` | `FEATURE_TARUTIL_ZERO_ALLOC_XATTR_AND_MAP_POOL=true` | Metrics Recorded | **KEEP** | `results/raw/v028-tarutil-ac8c/summary.md` |
