---
optimization:
  backend: optuna
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

## Constraints & Verification
- `benchmark_failures` == 0: All unit tests and benchmarks must pass cleanly. Data integrity must be strictly maintained (all decoded streams and merged snapshots must be byte-exact).
- Subagents can verify candidate code edits hermetically before proposing by running:
  ```bash
  go test -bench=. ./cmd/ateom-microvm/internal/ch/... ./cmd/atelet/internal/ategcs/... ./internal/tarutil/...
  ```

## Authorized Code Refactoring Scope
Mutations must be formulated as `[ACTION: CODE_REFACTOR]` proposals containing surgical source code patches across:
- `substrate/cmd/ateom-microvm/internal/ch/`
- `substrate/cmd/atelet/internal/ategcs/`
- `substrate/internal/tarutil/`
