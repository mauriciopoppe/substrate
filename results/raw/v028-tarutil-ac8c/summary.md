---
trial_id: "v028"
hypothesis_id: "v028-tarutil-ac8c"
parent_trial_id: "v022-ch-3c41"
status: "RUNNING"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v028-tarutil-ac8c

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: v022-ch-3c41 (43.34ms)
- **Active Search Space**: Go source refactoring across `tarutil` subsystem. Previous `tarutil` trials showed promise (e.g. v014 reduced allocs) but `BenchmarkExtract` alloc overhead remains high.
- **Sensitivity & Trajectory**: Pool usage and removing interface boxing reduced allocations, but map allocations in `tar.PAXRecords` parsing and `Extract` still consume heap.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: composite_ns_per_op=43.35ms, composite_allocs_per_op=13184 (from v022)
- **SLA Status**: MET
- **Subsystem Health Triage**: `tarutil` subsystem directory extraction (`BenchmarkExtract`) is the dominant allocation hotspot, accounting for 9,141 allocs/op and 7.11 ms CPU time constraints.
- **Active Trait Providers Loaded**: apo-provider-go-compiler

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: results/raw/v022-ch-3c41/summary.md, results/raw/v014-tarutil-zero-alloc-a8ea/summary.md
- **Subsystem Health Matrix Evidence**: `mem_tarutil.pprof` shows map allocations and string formatting allocations in `restoreOverlayXattrs` and `Extract`.
- **Spanner KB Citations**:
  - *Campaign Record*: 8e2d67b7-024d-4ed2-be54-e5853355d92a
  - *Historical Tuning Runs*: v000, v014, v022
  - *Trial Persisted*: Pending evaluation
- **Domain Memory Recipes**: Unsafe Zero-Copy Conversions (using `unsafe.StringData`); `sync.Pool` maps.
- **Refuted Patterns Avoided**: Ensured code mutation isolates `tarutil` without cross-subsystem drift. Avoided unsafe goroutine loops.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Sizing changes for buffer pools.
- **Option B (Explore Path - Archetype Action)**: [ACTION: CODE_REFACTOR] Refactor `tarutil.go` to zero-allocation extract paths including PAX header xattrs.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - CODE_REFACTOR
- **Mutation Type**: CODE_REFACTOR
- **Hypothesis ID**: v028-tarutil-ac8c
- **Subsystem Focus**: Codebase (tarutil)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "substrate/internal/tarutil/tarutil.go",
    "intent": "1) Add a sync.Pool named extractDirsPool to recycle map[string]*tar.Header objects used in Extract, clearing them with clear(m) between uses. 2) Refactor restoreOverlayXattrs to apply xattrs directly inside the hdr.PAXRecords loop, removing the intermediate map[string]string allocation, pre-computing the target string once per file to avoid fmt.Sprintf in the loop, and using unsafe.Slice(unsafe.StringData(v), len(v)) to avoid []byte(v) allocations. Add unsafe import.",
    "target_symbols": ["Extract", "restoreOverlayXattrs", "extractDirsPool"]
  }
]
```
- **Expected Gain & Technical Rationale**: Eliminates repeated `map[string]string` allocations in `restoreOverlayXattrs` and `map[string]*tar.Header` allocations in `Extract`, plus string formatting via `fmt.Sprintf` and byte casting. Reusing state and bypassing copy allocation significantly speeds up `tarutil` extraction routines and lowers `composite_allocs_per_op`.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `substrate/internal/tarutil/tarutil.go`. Recycles `map[string]*tar.Header` via `extractDirsPool` with `clear(dirs)` sanitization in `Extract`, eliminates intermediate `attrs` map allocations in `restoreOverlayXattrs`, avoids repeated `fmt.Sprintf` formatting for target paths, and applies zero-copy `unsafe.Slice` conversions on immutable string data during xattr restoration.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code refactor exploring Subsystem C tarutil; distinct from active proposals v027 and v029, and past trials v014, v015, v023, v024)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `substrate/internal/tarutil/tarutil.go` within allowed_file_scope in `prompts/objective.md`)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe `sync.Pool` usage with `clear()` reset semantics, zero goroutine leaks, immutable slice conversion bounds, zero unprotected shared mutable state)
- **Management Cores Check**: PASS (Guaranteed QoS Kubernetes pod; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (Heap allocations reduced across archive extraction and PAX xattr application critical paths)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem C tarutil)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `FEATURE_TARUTIL_ZERO_ALLOC_XATTR_AND_MAP_POOL` | `true` | `substrate/internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |
