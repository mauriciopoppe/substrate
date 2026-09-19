---
trial_id: "v012"
hypothesis_id: "v012-tarutil-4e84"
parent_trial_id: "v007-ch-sparse-buf-pool-3cb6"
status: "EXECUTED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v012-tarutil-4e84

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: `v007-ch-sparse-buf-pool-3cb6` (Champion Baseline).
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Trials `v007` explored Subsystem B (`ch`), achieving significant gains. Per rotation directives in `prompts/objective.md`, following saturation of primary gains in `ch`, the search pivots to Subsystem C (`tarutil`), guided by the previous trial's recommendation to explore zero-allocation extraction to tackle the high number of unit allocations.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 48,569,843 ns/op
  - `composite_bytes_per_op`: 26,561,940 B/op
  - `composite_allocs_per_op`: 14,080 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET
- **Subsystem Health Triage**: In Subsystem C (`substrate/internal/tarutil`), `BenchmarkExtract` currently accounts for 9,541 allocs/op (67.8% of all suite allocations) and 7.33 ms CPU time.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Direct slice passing & elimination of unnecessary `io.Reader`/`io.Writer` interface conversions.

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v007-ch-sparse-buf-pool-3cb6/summary.md`.
- **Subsystem Health Matrix Evidence**: `BenchmarkExtract` allocates extensively due to interface wrapper allocations. Each pooled `copyPooled` call escapes `writerOnly` and `readerOnly` into heap allocations.
- **Spanner KB Citations**: N/A
- **Domain Memory Recipes**: Reusable direct slice I/O paths bypassing interface-heavy stdlib wrapper chains.
- **Refuted Patterns Avoided**: N/A

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling. Refuted because this Go microbenchmark workspace has no external tunable environment variables.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]` targeting `substrate/internal/tarutil/tarutil.go`. Replaces `io.CopyBuffer` calls mapped through `writerOnly` and `readerOnly` with an inline `for` loop directly invoking `src.Read(buf)` and `dst.Write(buf)`. This fulfills the direct slice passing archetype, eliminating 2 escaping heap interface allocations per file extracted.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v012-tarutil-4e84`
- **Subsystem Focus**: `substrate/internal/tarutil`
- **Proposed Mutation Payload**:
  ```json
  [
    {
      "filename": "substrate/internal/tarutil/tarutil.go",
      "status": "modified",
      "patch": "@@ -75,13 +75,26 @@\n // copyPooled masks the fast-path interfaces so io.CopyBuffer uses the pooled buffer.\n func copyPooled(dst io.Writer, src io.Reader) (int64, error) {\n \tbp := copyBufPool.Get().(*[]byte)\n \tdefer copyBufPool.Put(bp)\n-\treturn io.CopyBuffer(writerOnly{dst}, readerOnly{src}, *bp)\n-}\n-\n-type writerOnly struct{ io.Writer }\n-type readerOnly struct{ io.Reader }\n+\tbuf := *bp\n+\tvar written int64\n+\tfor {\n+\t\tnr, er := src.Read(buf)\n+\t\tif nr > 0 {\n+\t\t\tnw, ew := dst.Write(buf[0:nr])\n+\t\t\tif nw > 0 {\n+\t\t\t\twritten += int64(nw)\n+\t\t\t}\n+\t\t\tif ew != nil {\n+\t\t\t\treturn written, ew\n+\t\t\t}\n+\t\t\tif nr != nw {\n+\t\t\t\treturn written, io.ErrShortWrite\n+\t\t\t}\n+\t\t}\n+\t\tif er != nil {\n+\t\t\tif er == io.EOF {\n+\t\t\t\tbreak\n+\t\t\t}\n+\t\t\treturn written, er\n+\t\t}\n+\t}\n+\treturn written, nil\n+}"
    }
  ]
  ```
- **Expected Gain & Technical Rationale**:
  - Eliminates 2 escaping heap interface allocations per file extraction. For thousands of files, this directly slashes `composite_allocs_per_op`.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/internal/tarutil/tarutil.go`. Replaces `writerOnly` and `readerOnly` interface boxing wrappers and `io.CopyBuffer` with a direct inlined slice `Read`/`Write` loop utilizing the pooled `copyBufPool` buffer. Eliminates 2 escaping heap interface allocations per file extracted while strictly adhering to `io.Reader`/`io.Writer` I/O contracts, zero-allocation conventions, and concurrency safety.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique mutation building on top of Champion `v007-ch-sparse-buf-pool-3cb6` and rotating to Subsystem C `tarutil`)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `substrate/internal/tarutil/tarutil.go`; no unauthorized scripts or config modified)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe `sync.Pool` usage with `defer copyBufPool.Put(bp)`, slice bounds safety, zero goroutine leaks, zero unprotected mutable global state)
- **Management Cores Check**: PASS (Microbenchmark pod runs with Guaranteed QoS; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (Heap interface allocations eliminated on file extraction hotpath)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem C `substrate/internal/tarutil`)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `tarutil.go (copyPooled inlined loop)` | `CODE_REFACTOR` | `substrate/internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |
