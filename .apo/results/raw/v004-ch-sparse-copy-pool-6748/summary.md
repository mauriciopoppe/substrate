---
trial_id: "v004"
hypothesis_id: "v004-ch-sparse-copy-pool-6748"
parent_trial_id: "v000"
status: "EXECUTED"
outcome: "CRASH"
strategy: "EXPLORE"
---

# Trial Summary: v004-ch-sparse-copy-pool-6748

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v000`: `composite_ns_per_op` = 59,491,529 ns/op (~59.5 ms), `composite_bytes_per_op` = 112,012,802 B/op (~106.8 MiB), `composite_allocs_per_op` = 14,081 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP / Champion Baseline)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/cmd/ateom-microvm/internal/ch/`, `substrate/cmd/atelet/internal/ategcs/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Initial baseline `v000` calibrated. Prior trials `v001`–`v003` explored `parzstd.go` in `ategcs` ($S_{\text{Engine}}$). Subsystem pivot to `ch` ($S_{\text{Storage}}$ / Sparse Memory Overlay Merging) targets un-tuned baseline memory allocations in `BenchmarkCopySparseRegions` and `BenchmarkMergeDeltaIntoBase`.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 59,491,529 ns/op
  - `composite_bytes_per_op`: 112,012,802 B/op (~106.8 MiB)
  - `composite_allocs_per_op`: 14,081 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (`benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - Target Subsystem: $S_{\text{Storage}}$ (`substrate/cmd/ateom-microvm/internal/ch/merge.go`).
  - Bottleneck Device Law: Operational analysis highlights that `BenchmarkCopySparseRegions` allocates 1,048,784 B/op (1.0 MiB) and `BenchmarkMergeDeltaIntoBase` allocates 1,051,024 B/op (1.0 MiB). Both allocations stem directly from allocating fresh 1 MiB scratch buffers (`buf := make([]byte, 1<<20)`) in `copySparseRegions`.
  - In addition to heap memory demand, allocating and zeroing 1 MiB on every invocation drives garbage collector invocation frequency (`runtime.mallocgc` / `runtime.gcBgMarkWorker`) and adds latency across the micro-VM memory overlay restore hotpath.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Go Language & Compiler Performance Trait Provider (Pattern 2: `sync.Pool` Struct & Buffer Arena Recycling; Concurrency Safety Rule 2: `sync.Pool` poisoning prevention).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**:
  - `results/raw/v000/summary.md`: Baseline metrics showing `ch.BenchmarkCopySparseRegions` (7,999,113 ns/op, 1,048,784 B/op, 2 allocs/op) and `ch.BenchmarkMergeDeltaIntoBase` (2,539,025 ns/op, 1,051,024 B/op, 28 allocs/op).
  - `results/raw/v001-ategcs-zstd-chunk-pool-d3ec/summary.md` & `results/raw/v002-ategcs-zstd-pool-9f9e/summary.md`: Judger feedback on physical diff scoping and concurrency safety.
- **Subsystem Health Matrix Evidence**:
  - `ch.BenchmarkCopySparseRegions`: 1,048,784 B/op is dominated by `make([]byte, 1<<20)` (1,048,576 bytes).
  - `ch.BenchmarkMergeDeltaIntoBase`: 1,051,024 B/op is dominated by `copySparseRegions` data copying.
- **Spanner KB Citations**:
  - *Campaign Record*: Fetched tuning history from Spanner KB (`safetune-kb-fetch-trial`).
  - *Historical Tuning Runs*: `0343eba5-73f0-4209-98f3-a7d08a6e6525`, `4aa00bed-2605-4b15-9975-be0f33a4414d`.
- **Domain Memory Recipes**: `~/memory/ubench-workload-optimization/SCHEMA.md` (Go memory arena and buffer pool recycling patterns).
- **Refuted Patterns Avoided**:
  - Unvetted file modifications: Diff modifies exclusively `substrate/cmd/ateom-microvm/internal/ch/merge.go`, adhering 100% to authorized scope in `prompts/objective.md`.
  - Slice poisoning / bounds corruption: Slice length is explicitly reset (`*bp = (*bp)[:1<<20]`) before returning to `sparseCopyBufPool`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric search infill is not applicable as this pure Go microbenchmark suite exposes no Optuna tunables in manifests; tuning relies on structural code refactoring.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`: Pivot from `ategcs` ($S_{\text{Engine}}$) to `ch` ($S_{\text{Storage}}$ / Sparse Memory Overlay Merging). Wrap the 1 MiB data region copy buffer in a package-level `sync.Pool` (`sparseCopyBufPool`) in `substrate/cmd/ateom-microvm/internal/ch/merge.go` so that calls to `copySparseRegions` reuse pre-allocated 1 MiB buffers instead of allocating on each merge.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` / `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v004-ch-sparse-copy-pool-6748`
- **Subsystem Focus**: `cmd/ateom-microvm/internal/ch` (Sparse Memory Overlay Merging)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "substrate/cmd/ateom-microvm/internal/ch/merge.go",
    "status": "modified",
    "patch": "--- a/substrate/cmd/ateom-microvm/internal/ch/merge.go\n+++ b/substrate/cmd/ateom-microvm/internal/ch/merge.go\n@@ -23,6 +23,7 @@\n \t\"io\"\n \t\"os\"\n \t\"os/exec\"\n+\t\"sync\"\n \n \t\"github.com/agent-substrate/substrate/cmd/ateom-microvm/internal/reaper\"\n \t\"golang.org/x/sys/unix\"\n@@ -174,6 +175,13 @@\n // at the same byte offsets, leaving dst's other bytes untouched. Holes in src are\n // located via SEEK_DATA/SEEK_HOLE and skipped. src and dst are assumed to be the\n // same logical size (the caller validates this).\n+var sparseCopyBufPool = sync.Pool{\n+\tNew: func() any {\n+\t\tb := make([]byte, 1<<20)\n+\t\treturn &b\n+\t},\n+}\n+\n func copySparseRegions(src, dst *os.File) (copied int64, err error) {\n \tsi, err := src.Stat()\n \tif err != nil {\n@@ -181,7 +189,12 @@\n \t}\n \tsize := si.Size()\n \tsfd := int(src.Fd())\n-\tbuf := make([]byte, 1<<20)\n+\tbp := sparseCopyBufPool.Get().(*[]byte)\n+\tdefer func() {\n+\t\t*bp = (*bp)[:1<<20]\n+\t\tsparseCopyBufPool.Put(bp)\n+\t}()\n+\tbuf := *bp\n \toff := int64(0)\n \tfor off < size {\n \t\t// Next populated region [ds, de) in src.\n"
  }
]
```
- **Expected Gain & Technical Rationale**:
  - Eliminates 1,048,576 bytes of heap allocation per call in `copySparseRegions`.
  - Drops `BenchmarkCopySparseRegions` memory from 1,048,784 B/op to ~208 B/op (>99.9% reduction).
  - Drops `BenchmarkMergeDeltaIntoBase` memory from 1,051,024 B/op to ~2,448 B/op (>99.7% reduction).
  - Combined elimination of >2 MiB heap allocations per iteration across both snapshot merge microbenchmarks, eliminating memory zeroing overhead and GC mark pressure.


## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Reuses 1 MiB scratch copy buffers via package-level `sync.Pool` (`sparseCopyBufPool`) with explicit slice length reset (`[:1<<20]`) and safe thread-safe defer return, eliminating ~2 MiB of heap allocations per iteration across sparse snapshot merging hotpaths while preserving data integrity and concurrency safety.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code mutation targeting previously unoptimized sparse memory overlay merging hotpath in `ch/merge.go`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to `substrate/cmd/ateom-microvm/internal/ch/merge.go` within authorized scope in `prompts/objective.md`; zero diff leakage)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe `sync.Pool` usage, slice length explicitly sanitized before pool return, no goroutine leaks, no unprotected mutable global state)
- **Management Cores Check**: PASS (Microbenchmark pod runs with Guaranteed QoS with 4 CPU, 8Gi RAM; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (Recycling 1 MiB buffers significantly reduces heap churn and GC mark worker pressure)
- **Layer & Subsystem Isolation**: PASS (Single subsystem layer modified: $S_{\text{Storage}}$ / $S_{\text{GoCompiler}}$)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `sparseCopyBufPool (sync.Pool 1MiB Buffer)` | `CODE_REFACTOR` | `substrate/cmd/ateom-microvm/internal/ch/merge.go` | `apo-provider-go-compiler` |
