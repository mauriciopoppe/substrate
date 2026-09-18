---
trial_id: "v015"
hypothesis_id: "v015-tarutil-75c2"
parent_trial_id: "v007-ch-sparse-buf-pool-3cb6"
status: "PROPOSED"
outcome: "UNJUDGED"
strategy: "EXPLORE"
---

# Trial Summary: v015-tarutil-75c2

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: `v007-ch-sparse-buf-pool-3cb6` and `v003-ategcs-zstd-chunk-pool-a8d7` (Outcome: KEEP / Champion Baselines)
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized across `substrate/internal/tarutil/`, `substrate/cmd/ateom-microvm/internal/ch/`, and `substrate/cmd/atelet/internal/ategcs/`.
- **Sensitivity & Trajectory**: Trials `v001` through `v007` explored Subsystem A (`ategcs`) and Subsystem B (`ch`), driving massive reductions in heap allocation volume via `parzstd.go` buffer pooling and `sparseCopyBufPool`. Per rotation directives in `prompts/objective.md` and explicit recommendation in `v007`, the search continues to Subsystem C (`tarutil`).

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: N/A (Based on champion baseline `v007` metrics proxying current state)
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0 in prior trials)
- **Subsystem Health Triage**:
  - In Subsystem C (`substrate/internal/tarutil`), `BenchmarkExtract` currently accounts for over 9,500 allocs/op, representing the majority of the suite's remaining heap object allocations.
  - Inspection of `tarutil.go` reveals two major sources of allocations per file entry: `hdr.FileInfo().Mode()` returning an interface per file, and `copyPooled(dst, src)` boxing value structs into `io.Writer` and `io.Reader` interfaces on each invocation of `io.CopyBuffer`.
- **Active Trait Providers Loaded**: 
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`, `results/raw/v007-ch-sparse-buf-pool-3cb6/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `tarutil.BenchmarkExtract`: 9,541 allocs/op (~67.8% of all suite allocations) and ~7.33 ms CPU time.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` arenas with pointer wrapper semantics to bypass interface boxing allocations.
- **Refuted Patterns Avoided**:
  - Avoiding breaking posix bits mapping by preserving the standard bit layout when deriving the permissions manually from the raw `tar.Header.Mode`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling. Refuted due to lack of environment-tunable variables in the benchmark test scope.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`. Replaces `copyPooled()` dynamic interface wrapping structs with a sync.Pool of pre-allocated `copyState` objects carrying pointer methods. Also fast-paths `hdr.FileInfo().Mode().Perm()` and `restoredMode` directly from `os.FileMode(hdr.Mode)`.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v015-tarutil-75c2`
- **Subsystem Focus**: `substrate/internal/tarutil` (Subsystem C)
- **Proposed Mutation Payload**: `{"files": [{"filename": "substrate/internal/tarutil/tarutil.go", "status": "modified", "patch": "..."}]}` (See CLI payload)
- **Expected Gain & Technical Rationale**:
  - Eliminates value boxing within `copyPooled` by utilizing a pointer method implementation cached in a pool.
  - Bypasses `FileInfo()` allocation overhead for file headers. Expected to drop allocations per operation by several hundreds, significantly alleviating GC overhead.
