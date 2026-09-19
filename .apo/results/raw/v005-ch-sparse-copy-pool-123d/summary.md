---
trial_id: "v005"
hypothesis_id: "v005-ch-sparse-copy-pool-123d"
parent_trial_id: "v003"
status: "EXECUTED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v005-ch-sparse-copy-pool-123d

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v003-ategcs-zstd-chunk-pool-a8d7`: `composite_ns_per_op` = 49,489,457 ns/op (-16.81%), `composite_bytes_per_op` = 28,807,617 B/op (-74.28%), `composite_allocs_per_op` = 14,085 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP / Champion Baseline)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/cmd/atelet/internal/ategcs/`, `substrate/cmd/ateom-microvm/internal/ch/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Trials `v001` through `v003` targeted `ategcs` (Subsystem A), reducing heap volume from 112.0 MiB to 28.8 MiB. Following the mandatory Subsystem Rotation order (`ategcs` -> `ch` -> `tarutil` -> `ategcs`) defined in `prompts/objective.md`, this iteration pivots to **Subsystem B (`ch`)** to address sparse memory overlay merging allocations.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 49,489,457 ns/op
  - `composite_bytes_per_op`: 28,807,617 B/op (~27.47 MiB/op)
  - `composite_allocs_per_op`: 14,085 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - In `substrate/cmd/ateom-microvm/internal/ch/merge.go`, `copySparseRegions` allocates a fresh 1 MiB (`1<<20` bytes) slice `buf := make([]byte, 1<<20)` on every call.
  - This single allocation dominates both `BenchmarkCopySparseRegions` (1,048,784 B/op) and `BenchmarkMergeDeltaIntoBase` (1,051,024 B/op), contributing ~2.1 MiB of recurring heap churn and invoking `runtime.mallocgc` on every microVM snapshot merge.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling), Concurrency Safety Rubric.

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `ch.BenchmarkCopySparseRegions`: 7,728,751 ns/op, 1,048,784 B/op, 2 allocs/op.
  - `ch.BenchmarkMergeDeltaIntoBase`: 2,528,923 ns/op, 1,051,024 B/op, 28 allocs/op.
- **Spanner KB Citations**: N/A (Pure Go microbenchmark workspace).
- **Domain Memory Recipes**: `sync.Pool` reusable byte slice arena for fixed-size 1 MiB copy buffers.
- **Refuted Patterns Avoided**:
  - Avoided cross-layer diff leakage by scoping edits exclusively to `substrate/cmd/ateom-microvm/internal/ch/merge.go`.
  - Guaranteed slice safety with deterministic buffer retrieval and `defer` pool return within `copySparseRegions`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Fine-tuning `parzstd` queue depths or worker counts. Rejected because `ategcs` has already been explored across 3 consecutive trials and Subsystem Rotation mandates pivoting to `ch`.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` + `[ACTION: CODE_REFACTOR]` targeting `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Introduces a package-level `sync.Pool` (`sparseCopyBufPool`) for the 1 MiB chunk copy buffer in `copySparseRegions`, eliminating 1 MiB heap allocations per merge operation.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` / `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v005-ch-sparse-copy-pool-123d`
- **Subsystem Focus**: `cmd/ateom-microvm/internal/ch` (Sparse Memory Overlay Merging Subsystem)
- **Proposed Mutation Payload**:
  ```json
  [
    {
      "filename": "substrate/cmd/ateom-microvm/internal/ch/merge.go",
      "status": "modified",
      "patch": "--- a/substrate/cmd/ateom-microvm/internal/ch/merge.go\n+++ b/substrate/cmd/ateom-microvm/internal/ch/merge.go\n@@ -25,6 +25,7 @@\n \t\"os\"\n \t\"os/exec\"\n+\t\"sync\"\n \n \t\"github.com/agent-substrate/substrate/cmd/ateom-microvm/internal/reaper\"\n \t\"golang.org/x/sys/unix\"\n@@ -30,6 +31,12 @@\n )\n \n+var sparseCopyBufPool = sync.Pool{\n+\tNew: func() any {\n+\t\treturn make([]byte, 1<<20)\n+\t},\n+}\n+\n // MergeSparseOverlay reconstructs a COMPLETE memory snapshot from an OnDemand\n // (userfaultfd) restore. CH's new snapshot (deltaFile) contains only the pages\n@@ -183,3 +190,4 @@\n \tsfd := int(src.Fd())\n-\tbuf := make([]byte, 1<<20)\n+\tbuf := sparseCopyBufPool.Get().([]byte)\n+\tdefer sparseCopyBufPool.Put(buf)\n \toff := int64(0)\n"
    }
  ]
  ```
- **Expected Gain & Technical Rationale**:
  - Eliminates the 1 MiB heap allocation in `copySparseRegions`, reducing `BenchmarkCopySparseRegions` heap volume from ~1.05 MiB to ~208 B (-99.98%) and `BenchmarkMergeDeltaIntoBase` heap volume from ~1.05 MiB to ~2.4 KiB (-99.7%).
  - Reduces composite heap bytes by ~2.1 MiB/op and relieves memory allocator pressure (`runtime.mallocgc`) during snapshot merge operations.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Reuses 1MiB sparse copy buffer via package-level `sync.Pool` (`sparseCopyBufPool`) with `defer` return in `copySparseRegions`, eliminating 1MiB heap slice allocations per merge operation while maintaining thread-safety, byte-exact data integrity, and strict isolation within the authorized codebase scope.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code mutation targeting Subsystem B `ch`, distinct from previous trials `v000`-`v003`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to `substrate/cmd/ateom-microvm/internal/ch/merge.go` within authorized scope in `prompts/objective.md`; no unvetted structural diffs)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Standard safe `sync.Pool` buffer pattern, no goroutine leaks, no poisoning, safe concurrent retrieval and defer return)
- **Management Cores Check**: PASS (Microbenchmark runs in Kubernetes Pod with Guaranteed QoS; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (1MiB buffer recycling eliminates major memory allocation hotpath in `copySparseRegions` and `MergeDeltaIntoBase`)
- **Layer & Subsystem Isolation**: PASS (S_Substrate / Subsystem B `ch` only)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `ch/merge.go (sync.Pool sparse copy buffer)` | `CODE_REFACTOR` | `substrate/cmd/ateom-microvm/internal/ch/merge.go` | `apo-provider-go-compiler` |
