---
optimization:
  backend: optuna
  allowed_file_scope:
    - substrate/cmd/ateom-microvm/internal/ch/
    - substrate/cmd/atelet/internal/ategcs/
    - substrate/internal/tarutil/
  metrics:
    - name: composite_ns_per_op
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 3.0
    - name: composite_bytes_per_op
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 1.0
    - name: composite_allocs_per_op
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 1.0
  constraints:
    - metric: benchmark_failures
      max: 0
---

# Workload Optimization Objective: Substrate Core Hotpath Go Microbenchmarks

Optimize the pure Go source code of the Agent Substrate runtime components (`cmd/ateom-microvm/internal/ch`, `cmd/atelet/internal/ategcs`, and `internal/tarutil`) to minimize CPU latency (`composite_ns_per_op`), heap allocation volume (`composite_bytes_per_op`), and heap allocation count (`composite_allocs_per_op`) across the snapshot and restore critical path.

## Benchmark Hotpaths Under Optimization
The benchmark suite evaluates three primary components executed during actor suspend, snapshot upload, snapshot download, and actor resume:
1. **Sparse Memory Overlay Merging (`cmd/ateom-microvm/internal/ch/merge.go`)**:
   - `BenchmarkMergeDeltaIntoBase`: Renames base snapshot and overlays dirty delta pages into place.
   - `BenchmarkCopySparseRegions`: Scans populated regions using `unix.Seek` (`SEEK_DATA`/`SEEK_HOLE`) and copies data chunks.
2. **Sparse Extent Compression & Decompression (`cmd/atelet/internal/ategcs/sparsezstd.go`)**:
   - `BenchmarkWriteSparseZstd`: Incremental extent scanning and parallel zstd chunk compression.
   - `BenchmarkReadSparseZstd`: Streaming decompression and reconstruction of sparse disk images.
3. **Rootfs Upper Layer Packaging (`internal/tarutil/tarutil.go`)**:
   - `BenchmarkExtract`: Streaming extraction of overlay upper directories and metadata restoration.
   - `BenchmarkCreate`: Tar archiving of directory trees while preserving file modes, device nodes, and xattrs.

## Target Objectives
1. `composite_ns_per_op` (Minimize): Sum of CPU execution time per operation across the hotpaths.
2. `composite_bytes_per_op` (Minimize): Total heap bytes allocated per operation.
3. `composite_allocs_per_op` (Minimize): Total heap object allocations per operation.

## Constraints
- `benchmark_failures` == 0: All unit tests and benchmarks must pass cleanly in staged benchmark runs. Data integrity must be strictly maintained (all decoded streams and merged snapshots must be byte-exact).

## Allowed File Scope & Refactoring Boundaries
Mutations must be formulated strictly as pure Go source code refactors (`[ACTION: CODE_REFACTOR]`) containing surgical patches across:
- `substrate/cmd/ateom-microvm/internal/ch/*.go` (including `merge.go`, `prefault.go`, `createvm.go`, `restorefds.go`, `guestclock.go`, `api.go`, and companion tests `*_test.go`)
- `substrate/cmd/atelet/internal/ategcs/*.go` (including `sparsezstd.go`, `parzstd.go`, `gcssparse.go`, `sparseparts.go`, `rangedget.go`, `objects.go`, `s3.go`, `gcs.go`, and companion tests `*_test.go`)
- `substrate/internal/tarutil/*.go` (including `tarutil.go`, `owner_linux.go`, `fifo_linux.go`, and companion tests `*_test.go`)

### Strictly Prohibited Files
To ensure reproducibility and isolate performance gains to algorithmic and memory-efficiency improvements in Go:
- **DO NOT MODIFY** `build.sh`, `set-env.sh`, `run_experiment.sh`, or any shell scripts.
- **DO NOT MODIFY** `manifests/` (e.g. `manifests/tunables.env`) or any deployment/environment configuration files.
- **DO NOT MODIFY** packages outside the three hotpath subsystems (`ch`, `ategcs`, `tarutil`).

### Candidate Generation Directives & Hot-Path Focus

#### Subsystem Architecture & Target Hotpaths
To ensure comprehensive exploration and prevent hyper-local optimization within a single component, the Generator must track and rotate across the three distinct runtime subsystems:
1. **Subsystem A (`ategcs`)**:
   - Extent serialization, format framing, and streaming decompression (`substrate/cmd/atelet/internal/ategcs/sparsezstd.go`).
   - Parallel multi-threaded zstd chunk encoding, worker routine buffer pools, chunk synchronization, and GCS/S3 streaming parts (`substrate/cmd/atelet/internal/ategcs/parzstd.go`, `sparseparts.go`, `gcssparse.go`).
   - Benchmark harness caller co-refactoring (`substrate/cmd/atelet/internal/ategcs/sparsezstd_bench_test.go`).
2. **Subsystem B (`ch`)**:
   - Sparse memory overlay merging, hole scanning with `unix.Seek` (`SEEK_DATA`/`SEEK_HOLE`), and positional block copying (`substrate/cmd/ateom-microvm/internal/ch/merge.go`).
   - File descriptor and memory pre-faulting routines (`substrate/cmd/ateom-microvm/internal/ch/prefault.go`, `restorefds.go`).
   - Benchmark harness caller co-refactoring (`substrate/cmd/ateom-microvm/internal/ch/merge_bench_test.go`).
3. **Subsystem C (`tarutil`)**:
   - Rootfs archive streaming, upper layer packaging, directory extraction, and PAX extended attributes (`substrate/internal/tarutil/tarutil.go`).
   - Inode identification, link counting, FIFO handling, and file stat caching (`substrate/internal/tarutil/owner_linux.go`, `fifo_linux.go`).
   - Benchmark harness caller co-refactoring (`substrate/internal/tarutil/tarutil_bench_test.go`).

#### Preferred Exploration Archetypes & Recipes
- Zero-allocation buffer reuse: Replace per-operation slice allocations with pooled buffers (`sync.Pool` with reset semantics).
- Sliced and chunked processing: Optimize buffer size thresholds for I/O and compression chunks to avoid heap escapes.
- Lock contention reduction: Minimize critical section duration and avoid global locks on hot reader paths.
- Direct slice passing: Eliminate unnecessary intermediate conversions between `[]byte` and `io.Reader`/`io.Writer`.
- Inode and metadata caching: Reuse stat buffers and link maps to minimize syscall and allocation overhead.

### Anti-Stagnation & Convergence Policy
- **Historical Analysis Required**: Before formulating a new hypothesis, the Generator MUST inspect prior living trial summaries (`results/raw/<trial_id>/summary.md`) and the recent changelog ledger to identify refuted patterns, rejected approaches, and regressions.
- **Stagnation Circuit Breaker**: If 3 consecutive trials targeting a specific subsystem produce non-improving results (status `REJECTED`, outcome `DISCARD`, or metric gain < 5%), that subsystem enters state `STALLED`.
- **Mandatory Subsystem Pivot (`[ACTION: SUBSYSTEM_PIVOT]`)**: When a subsystem is `STALLED`, the Generator is strictly prohibited from proposing further changes to that subsystem. It MUST pivot to the next active or unexplored subsystem in rotation order (`ategcs` -> `ch` -> `tarutil` -> `ategcs`).
- **Archetype Diversity Guardrail**: The Generator must avoid proposing more than 2 consecutive variations of the exact same optimization technique within a subsystem (e.g., after 2 pool buffer size variations, pivot to concurrency, streaming chunking, or I/O syscall optimization).


