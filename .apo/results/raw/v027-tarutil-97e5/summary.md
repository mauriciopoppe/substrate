---
trial_id: "v027"
hypothesis_id: "v027-tarutil-97e5"
parent_trial_id: "v022-ch-3c41"
status: "EXECUTED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v027-tarutil-97e5

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: v022-ch-3c41 (43.3ms, 13184 allocs/op)
- **Active Search Space**: `ch`, `ategcs`, `tarutil` Subsystems pure Go source code.
- **Sensitivity & Trajectory**: v022 successfully optimized userspace I/O boundary layers in `ch` subsystem via in-kernel slice operations, driving total CPU latency lower. However, Subsystem `tarutil` remains the predominant heap allocation bottleneck, driving 9141 allocs/op (69.3% in `BenchmarkExtract`) and 3901 allocs/op (29.6% in `BenchmarkCreate`).

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: From v022 Champion: `BenchmarkExtract`=9141 allocs/op; `BenchmarkCreate`=3901 allocs/op.
- **SLA Status**: MET (0 benchmark failures)
- **Subsystem Health Triage**: Subsystem C (`tarutil`) is generating excess GC overhead due to per-entry map[string]string allocations via `readOverlayXattrs`, temporary string slice allocations during extraction inside `restoreOverlayXattrs`, and holding heavily-allocated `*tar.Header` structs unnecessarily retaining massive heap footprints.
- **Active Trait Providers Loaded**: apo-provider-go-compiler

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v022-ch-3c41/summary.md`, `results/raw/v018-ategcs-a6ad/summary.md`
- **Subsystem Health Matrix Evidence**: `v018` explicitly noted: "Follow up on zero-allocation tar header extraction, stat caching, and pool recycling in tarutil.go".
- **Spanner KB Citations**: N/A
- **Domain Memory Recipes**: Go sync.Pool recycling; zero-allocation primitives for xattr boundaries; value-type semantic structs for map storage over pointers.
- **Refuted Patterns Avoided**: N/A

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Not applicable (no parametric bounds to scale).
- **Option B (Explore Path - Archetype Action)**: `[ACTION: CODE_REFACTOR]` applying "Zero-allocation buffer reuse" to bypass `map[string]string` reconstruction entirely, leverage `sync.Pool` for xattr processing buffers, and downcast mapping payloads for retained metadata to plain `dirMeta` structs.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - CODE_REFACTOR
- **Mutation Type**: CODE_REFACTOR
- **Hypothesis ID**: v027-tarutil-97e5
- **Subsystem Focus**: `internal/tarutil`
- **Proposed Mutation Payload**: 
```json
[
  {
    "filename": "internal/tarutil/tarutil.go",
    "intent": "Refactor readOverlayXattrs into readOverlayXattrsInto(path string, hdr *tar.Header) using a sync.Pool byte slice buffer to populate hdr.PAXRecords directly, eliminating per-file map and slice heap escapes. Refactor restoreOverlayXattrs to iterate hdr.PAXRecords directly without building a temporary map[string]string. Optimize directory metadata retention in Extract by storing a lightweight dirMeta struct instead of *tar.Header pointers to reduce heap volume.",
    "target_symbols": ["readOverlayXattrs", "writeTree", "Extract", "restoreOverlayXattrs"]
  }
]
```
- **Expected Gain & Technical Rationale**: Reusing byte buffers to retrieve xattr limits allocating two array-buffers per entry during archive serialization. Refusing to reconstruct temporary `attrs map[string]string` skips dynamic string operations in extraction (reducing allocs for prefix parsing). Using a distinct inner struct `dirMeta` for the `dirs` map avoids holding all `*tar.Header` structs via pointers and dragging down GC throughput.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `internal/tarutil/tarutil.go`. Refactors `readOverlayXattrs` into `readOverlayXattrsInto` using pooled scratch buffers to populate `hdr.PAXRecords` directly, iterates `hdr.PAXRecords` in `restoreOverlayXattrs` without intermediate map allocations, and substitutes `*tar.Header` with lightweight `dirMeta` struct in `Extract` to reduce heap footprint while strictly preserving POSIX setuid, setgid, and sticky bits.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code refactor exploring Subsystem C tarutil; distinct from trials v014, v015, v024, v028, and v029)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to authorized component `internal/tarutil/tarutil.go` within allowed_file_scope)
- **Domain Trait & Concurrency Check**: PASS (apo-provider-go-compiler: Thread-safe `sync.Pool` usage with bounded buffer capacity, zero goroutine leaks, zero unprotected shared mutable state)
- **Management Cores Check**: PASS (Guaranteed QoS pod; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (Heap allocations reduced across archive xattr reading, extraction, and directory metadata retention)
- **Layer & Subsystem Isolation**: PASS (Single subsystem modified: Subsystem C tarutil)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `FEATURE_ZERO_ALLOC_TARUTIL_XATTRS` | `true` | `internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |
