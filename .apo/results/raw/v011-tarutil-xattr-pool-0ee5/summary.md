---
trial_id: "v011"
hypothesis_id: "v011-tarutil-xattr-pool-0ee5"
parent_trial_id: "v003-ategcs-zstd-chunk-pool-a8d7"
status: "EXECUTED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v011-tarutil-xattr-pool-0ee5

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v003-ategcs-zstd-chunk-pool-a8d7` (Parent Champion): `CPU latencies (ch, ategcs, tarutil)` = 49,489,457 ns/op, `total_bytes_per_op` = 28,807,617 B/op, `total_allocs_per_op` = 14,085 allocs/op, `benchmark_failures` = 0.
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `cmd/atelet/internal/ategcs/`, `cmd/ateom-microvm/internal/ch/`, and `internal/tarutil/`.
- **Sensitivity & Trajectory**: Following the Subsystem Rotation instructions in `prompts/objective.md` (`ategcs` -> `ch` -> `tarutil` -> `ategcs`), and observing that Subsystem B (`ch`) repeatedly failed or stalled in trials v004-v010 (crashing or yielding regressions / cancellations), the optimization Engine pivots to Subsystem C (`tarutil`).

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics (from baseline v003)**:
  - `CPU latencies (ch, ategcs, tarutil)`: 49,489,457 ns/op
  - `total_bytes_per_op`: 28,807,617 B/op
  - `total_allocs_per_op`: 14,085 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - Subsystem C (`tarutil`) processes rootfs archive streaming in `BenchmarkExtract` and `BenchmarkCreate`.
  - Core hotspot localized to `readOverlayXattrs` which systematically allocates two independent dynamically-sized buffers (`buf := make([]byte, sz)` and `val := make([]byte, vsz)`) per file entry while reading extended attributes via `unix.Llistxattr` and `unix.Lgetxattr`. In trees with tens of thousands of files or heavily augmented metadata, these allocations cause substantial heap volume inflation and memory fragmentation.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`, `results/raw/v010-ch-sparse-copy-pool-8964/summary.md`.
- **Subsystem Health Matrix Evidence**: `tarutil.go` iterates all archived directories and reads `xattrs` dynamically inside `readOverlayXattrs`, allocating raw buffers linearly proportional to filesystem node counts.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` byte slice buffer arenas with dynamic expansion and lock-free thread-local retrieval to eliminate file-by-file heap escape.
- **Refuted Patterns Avoided**:
  - Pivoted away from `ch/merge.go` buffer pool modifications which stalled / collapsed over `v004-v010`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric sampling or tuning in `ch` subsystem. Refuted because `ch` modifications stalled and the objective commands a pivot (`[ACTION: SUBSYSTEM_PIVOT]`).
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` and `[ACTION: CODE_REFACTOR]` targeting `internal/tarutil/tarutil.go`. Implements a `sync.Pool` based `xattrBufPool` buffer to recycle byte slices when extracting overlayfs attributes `buf` and `val` in `readOverlayXattrs`.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` / `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: CODE_REFACTOR
- **Hypothesis ID**: v011-tarutil-xattr-pool-0ee5
- **Subsystem Focus**: `internal/tarutil` (Rootfs archive streaming)
- **Proposed Mutation Payload**: `JSON files[].patch` for `tarutil.go` replacing `make([]byte)` with `sync.Pool.Get()`.
- **Expected Gain & Technical Rationale**:
  - Completely drops the `make([]byte, sz)` and `make([]byte, vsz)` heap allocations per file scanned in `readOverlayXattrs` across the `BenchmarkCreate` workload.
  - Reduces `total_bytes_per_op` and `total_allocs_per_op` roughly proportionally to the total number of files in the simulated tar archive workload.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in `internal/tarutil/tarutil.go`. Reuses 8KB extended attribute buffers via package-level `sync.Pool` (`xattrBufPool`) with proper local scope `defer Put`, dynamic capacity expansion, and immutable string copy extraction, eliminating continuous heap allocations during rootfs archive xattr scanning while preserving concurrency safety and data integrity.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code mutation targeting tarutil xattr buffer allocation)
- **Physical Diff Audit**: PASS (Surgically scoped strictly to `internal/tarutil/tarutil.go` within authorized scope in `prompts/objective.md`; no diff leakage)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Thread-safe pool retrieval with defer release, dynamic resizing, no goroutine leaks or unprotected shared state)
- **Management Cores Check**: PASS (Microbenchmark pod has Guaranteed QoS with 4 CPU, 8Gi RAM; node management cores unperturbed)
- **Memory Headroom & OOM Guard**: PASS (Recycling 8KB slices drops heap churn and GC pressure)
- **Layer & Subsystem Isolation**: PASS (S_Substrate / S_GoCompiler / Subsystem C `tarutil` only)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `tarutil.go (xattrBufPool sync.Pool)` | `CODE_REFACTOR` | `internal/tarutil/tarutil.go` | `apo-provider-go-compiler` |
