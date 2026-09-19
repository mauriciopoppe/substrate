---
trial_id: "v010"
hypothesis_id: "v010-ch-sparse-copy-pool-8964"
parent_trial_id: "v003-ategcs-zstd-chunk-pool-a8d7"
status: "CANCELED"
outcome: "CANCELED"
strategy: "EXPLORE"
---

# Trial Summary: v010-ch-sparse-copy-pool-8964

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v003-ategcs-zstd-chunk-pool-a8d7` (Parent Champion): `composite_ns_per_op` = 49,489,457 ns/op (~49.5 ms), `composite_bytes_per_op` = 28,807,617 B/op (~27.5 MiB), `composite_allocs_per_op` = 14,085 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP / Champion).
  - `v000` (Initial Calibration Baseline): `composite_ns_per_op` = 59,491,529 ns/op, `composite_bytes_per_op` = 112,012,802 B/op, `composite_allocs_per_op` = 14,081 allocs/op, `benchmark_failures` = 0.
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/cmd/atelet/internal/ategcs/`, `substrate/cmd/ateom-microvm/internal/ch/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Trials `v001`-`v003` explored Subsystem A (`ategcs`), reducing heap allocation volume by -74.3% (from 112.0 MiB to 28.8 MiB). Following the Mandatory Subsystem Pivot policy (`[ACTION: SUBSYSTEM_PIVOT]`), optimization now rotates to Subsystem B (`ch` - Sparse Memory Overlay Merging & Kernel Sparse Region Copying) to address remaining heap allocation bottlenecks.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 49,489,457 ns/op
  - `composite_bytes_per_op`: 28,807,617 B/op (~27.5 MiB)
  - `composite_allocs_per_op`: 14,085 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - In Subsystem B (`cmd/ateom-microvm/internal/ch/merge.go`), `BenchmarkMergeDeltaIntoBase` (2,528,923 ns/op, 1,051,024 B/op) and `BenchmarkCopySparseRegions` (7,728,751 ns/op, 1,048,784 B/op) consume ~2.1 MiB of heap allocations per benchmark run.
  - Root cause localized to `copySparseRegions()` allocating a fresh 1 MiB scratch slice on every invocation: `buf := make([]byte, 1<<20)`.
  - Because `copySparseRegions` is invoked on every memory snapshot merge across actor suspend/resume workflows, allocating 1 MiB buffers triggers avoidable runtime allocator overhead (`runtime.mallocgc`) and GC background mark duty.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling), Concurrency Safety Check (thread-safe pooling, slice pointer sanitization).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `BenchmarkCopySparseRegions`: 7,728,751 ns/op, 1,048,784 B/op, 2 allocs/op.
  - `BenchmarkMergeDeltaIntoBase`: 2,528,923 ns/op, 1,051,024 B/op, 28 allocs/op.
  - Telemetry reveals 1,048,576 byte slice allocations inside `ch.copySparseRegions`.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` byte slice buffer arenas with zero-allocation retrieval and return.
- **Refuted Patterns Avoided**:
  - Avoided out-of-scope file modifications (`build.sh`, `set-env.sh`) that caused v001 rejection.
  - Avoided mutating non-authorized directories.
  - Avoided buffer slicing corruption by maintaining full 1 MiB capacity in `sync.Pool` and slicing within `io.ReadFull`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Further parametric tuning in `ategcs`. Refuted due to Mandatory Subsystem Pivot policy (`ategcs` completed in `v003`, pivot to `ch`).
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` and `[ACTION: CODE_REFACTOR]` targeting `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Introduces package-level `sparseCopyBufPool` (`sync.Pool`) for the 1 MiB scratch buffer in `copySparseRegions()`, recycling buffers across calls and eliminating heap churn.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` / `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v010-ch-sparse-copy-pool-8964`
- **Subsystem Focus**: `cmd/ateom-microvm/internal/ch` (Sparse Memory Overlay Merging & Copying)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "substrate/cmd/ateom-microvm/internal/ch/merge.go",
    "status": "modified",
    "patch": "--- a/substrate/cmd/ateom-microvm/internal/ch/merge.go\n+++ b/substrate/cmd/ateom-microvm/internal/ch/merge.go\n@@ -25,6 +25,7 @@\n \t\"io\"\n \t\"os\"\n \t\"os/exec\"\n+\t\"sync\"\n \n \t\"github.com/agent-substrate/substrate/cmd/ateom-microvm/internal/reaper\"\n \t\"golang.org/x/sys/unix\"\n@@ -172,13 +173,21 @@\n \treturn os.Rename(merged, deltaFile)\n }\n \n+var sparseCopyBufPool = sync.Pool{\n+\tNew: func() any {\n+\t\tb := make([]byte, 1<<20)\n+\t\treturn &b\n+\t},\n+}\n+\n // copySparseRegions overwrites dst with every populated (non-hole) region of src\n // at the same byte offsets, leaving dst's other bytes untouched. Holes in src are\n // located via SEEK_DATA/SEEK_HOLE and skipped. src and dst are assumed to be the\n // same logical size (the caller validates this).\n func copySparseRegions(src, dst *os.File) (copied int64, err error) {\n \tsi, err := src.Stat()\n \tif err != nil {\n \t\treturn 0, err\n \t}\n \tsize := si.Size()\n \tsfd := int(src.Fd())\n-\tbuf := make([]byte, 1<<20)\n+\tbp := sparseCopyBufPool.Get().(*[]byte)\n+\tdefer sparseCopyBufPool.Put(bp)\n+\tbuf := *bp\n \toff := int64(0)\n"
  }
]
```
- **Expected Gain & Technical Rationale**:
  - Eliminates the 1 MiB heap allocation in `copySparseRegions`, dropping heap allocation volume in `BenchmarkCopySparseRegions` from ~1.05 MiB to near 0 B/op and reducing `BenchmarkMergeDeltaIntoBase` heap allocations by ~99%.
  - Relieves GC pressure and eliminates memory allocation pause times during sparse memory merging.

## [CANCELED]
- Reason: Parent v003-ategcs-zstd-chunk-pool-a8d7 dominated on Pareto frontier
