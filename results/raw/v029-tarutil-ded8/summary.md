---
trial_id: "v029"
hypothesis_id: "v029-tarutil-ded8"
parent_trial_id: "v022-ch-3c41"
status: "CANCELED"
outcome: "CANCELED"
strategy: "EXPLORE"
---

# Trial Summary: v029-tarutil-ded8

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: v022-ch-3c41, v018-ategcs-a6ad, v019-ategcs-0472, v021-ch-53ce, v023-ategcs-798b
- **Active Search Space**: Go source refactoring across `tarutil` subsystem.
- **Sensitivity & Trajectory**: Pool usage and kernel splicing significantly reduced allocations and CPU cycles in `ch` and `ategcs`. Subsystem C (`tarutil`) remains the dominant source of heap memory allocations.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**: (From v022-ch-3c41) composite_ns_per_op: 43.34 ms, composite_bytes_per_op: 12.75 MB, composite_allocs_per_op: 13,184 allocs.
- **SLA Status**: MET
- **Subsystem Health Triage**: Subsystem C (`substrate/internal/tarutil`): `BenchmarkExtract` is the dominant allocation hotspot, accounting for 9,141 allocs/op (69.3% of all suite allocations). `BenchmarkCreate` accounts for a further 3,901 allocs/op. High allocation counts correlate with dynamic map allocations (`dirs map[string]*tar.Header`) and `readOverlayXattrs` byte slice parsing on every file.
- **Active Trait Providers Loaded**: `apo-provider-go-compiler`

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v022-ch-3c41/summary.md`
- **Subsystem Health Matrix Evidence**: Identified repetitive map allocations across `Extract` and non-pooled buffer use within xattr-fetching code sections (`readOverlayXattrs`), leading to massive heap object churn on deep directories.
- **Spanner KB Citations**: N/A
- **Domain Memory Recipes**: Reusable `sync.Pool` for slices and byte buffers.
- **Refuted Patterns Avoided**: N/A

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Not applicable (no parametric bounds to sample).
- **Option B (Explore Path - Archetype Action)**: `[ACTION: CODE_REFACTOR]`. Resolves map allocations natively present during rootfs structure deserialization and reduces byte slice garbage via `sync.Pool`.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - CODE_REFACTOR
- **Mutation Type**: CODE_REFACTOR
- **Hypothesis ID**: v029-tarutil-ded8
- **Subsystem Focus**: `substrate/internal/tarutil` (Subsystem C)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "substrate/internal/tarutil/tarutil.go",
    "intent": "Implement sync.Pool recycling for the extraction directory slice (replacing map[string]*tar.Header in Extract) and pool the byte slices used in readOverlayXattrs, eliminating repetitive memory allocations.",
    "target_symbols": ["Extract", "restoreDirMeta", "readOverlayXattrs"]
  }
]
```
- **Expected Gain & Technical Rationale**:
  - Replacing the `dirs` map with a pooled slice of structs (`extractedDir`) in `Extract` and `restoreDirMeta` will eliminate the map and key allocation overhead generated per archived directory.
  - Adding a `sync.Pool` for byte buffers in `readOverlayXattrs` will dramatically decrease garbage generation for xattr retrieval operations on every single stored file.

## [CANCELED]
- Reason: Parent v022-ch-3c41 dominated on Pareto frontier
