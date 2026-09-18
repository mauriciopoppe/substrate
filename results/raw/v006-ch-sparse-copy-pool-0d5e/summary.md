---
trial_id: "v006"
hypothesis_id: "v006-ch-sparse-copy-pool-0d5e"
parent_trial_id: "v003"
status: "EXECUTED"
outcome: "VALIDATED"
strategy: "EXPLORE"
---

# Trial Summary: v006-ch-sparse-copy-pool-0d5e

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**:
  - `v003-ategcs-zstd-chunk-pool-a8d7` (Pareto Champion Baseline): `composite_ns_per_op` = 49,489,457 ns/op (-16.8% vs v000), `composite_bytes_per_op` = 28,807,617 B/op (-74.3% vs v000), `composite_allocs_per_op` = 14,085 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP).
  - `v000` (Initial Baseline): `composite_ns_per_op` = 59,491,529 ns/op, `composite_bytes_per_op` = 112,012,802 B/op, `composite_allocs_per_op` = 14,081 allocs/op, `benchmark_failures` = 0 (Outcome: KEEP).
- **Active Search Space**: Pure Go codebase source mutations (`CODE_REFACTOR`) authorized under `prompts/objective.md` across `substrate/cmd/ateom-microvm/internal/ch/`, `substrate/cmd/atelet/internal/ategcs/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Trials `v001`, `v002`, and `v003` exhausted the initial optimization cycle on Subsystem A (`ategcs`), reducing heap allocation from 106.8 MiB to 27.5 MiB. In accordance with the Anti-Stagnation & Subsystem Rotation policy in `prompts/objective.md` (`ategcs` -> `ch` -> `tarutil`), the generator executes a mandatory subsystem pivot (`[ACTION: SUBSYSTEM_PIVOT]`) to Subsystem B (`ch`).

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 49,489,457 ns/op
  - `composite_bytes_per_op`: 28,807,617 B/op (~27.5 MiB)
  - `composite_allocs_per_op`: 14,085 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (All constraints satisfied; `benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - Subsystem B (`cmd/ateom-microvm/internal/ch/merge.go`) is responsible for memory overlay merging on the critical path of guest restore and suspend.
  - In `merge.go`, `copySparseRegions` allocates a fresh 1 MiB scratch buffer (`buf := make([]byte, 1<<20)`) on every invocation, generating 1,048,784 B/op in `BenchmarkCopySparseRegions` and 1,051,024 B/op in `BenchmarkMergeDeltaIntoBase`.
  - Furthermore, `copySparseRegions` repeatedly bounces extent data through user-space memory (`io.ReadFull` / `dst.Write`) even when operating on the same underlying local filesystem, incurring syscall transition overhead and cache thrashing.
- **Active Trait Providers Loaded**:
  - `apo-provider-go-compiler`: Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling), zero-allocation buffer reuse, in-kernel zero-copy (`unix.CopyFileRange`).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`, `results/raw/v003-ategcs-zstd-chunk-pool-a8d7/summary.md`.
- **Subsystem Health Matrix Evidence**:
  - `ch.BenchmarkCopySparseRegions`: 7,728,751 ns/op (~7.73 ms), 1,048,784 B/op (~1.0 MiB), 2 allocs/op.
  - `ch.BenchmarkMergeDeltaIntoBase`: 2,528,923 ns/op (~2.53 ms), 1,051,024 B/op (~1.0 MiB), 28 allocs/op.
  - Telemetry identifies 1 MiB slice allocations inside `copySparseRegions` on every snapshot merge.
- **Spanner KB Citations**: N/A (Pure Go software microbenchmark workspace).
- **Domain Memory Recipes**: Reusable `sync.Pool` buffer arenas, in-kernel zero-copy file range splicing (`unix.CopyFileRange`).
- **Refuted Patterns Avoided**:
  - Avoided editing files outside the authorized scope (`prompts/objective.md`), targeting strictly `substrate/cmd/ateom-microvm/internal/ch/merge.go`.
  - Avoided unbacked `CopyFileRange` assumptions by providing a fallback to pooled buffer streaming if `unix.CopyFileRange` returns an error or unsupported filesystem code.
  - Avoided buffer pool retention/leaks by allocating a pointer to slice `*[]byte` in `sparseRegionBufPool` and properly recycling with `defer sparseRegionBufPool.Put(bp)`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Further tuning of `ategcs` chunk buffer thresholds. Refuted because 3 consecutive trials already targeted `ategcs`, triggering the mandatory subsystem rotation policy.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: SUBSYSTEM_PIVOT]` & `[ACTION: CODE_REFACTOR]` targeting `substrate/cmd/ateom-microvm/internal/ch/merge.go`. Introduces in-kernel zero-copy `unix.CopyFileRange` for extent copying combined with a package-level `sync.Pool` buffer pool (`sparseRegionBufPool`) fallback, eliminating 1 MiB per-operation allocations and minimizing CPU latency.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: SUBSYSTEM_PIVOT]` / `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v006-ch-sparse-copy-pool-0d5e`
- **Subsystem Focus**: `cmd/ateom-microvm/internal/ch` (Sparse Memory Overlay & Delta Merger)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "substrate/cmd/ateom-microvm/internal/ch/merge.go",
    "status": "modified",
    "patch": "--- a/substrate/cmd/ateom-microvm/internal/ch/merge.go\n+++ b/substrate/cmd/ateom-microvm/internal/ch/merge.go\n@@ -25,6 +25,7 @@\n \t\"os\"\n \t\"os/exec\"\n+\t\"sync\"\n \n \t\"github.com/agent-substrate/substrate/cmd/ateom-microvm/internal/reaper\"\n \t\"golang.org/x/sys/unix\"\n@@ -172,13 +173,22 @@\n \treturn os.Rename(merged, deltaFile)\n }\n \n+var sparseRegionBufPool = sync.Pool{\n+\tNew: func() any {\n+\t\tb := make([]byte, 1<<20)\n+\t\treturn &b\n+\t},\n+}\n+\n // copySparseRegions overwrites dst with every populated (non-hole) region of src\n // at the same byte offsets, leaving dst's other bytes untouched. Holes in src are\n // located via SEEK_DATA/SEEK_HOLE and skipped. src and dst are assumed to be the\n // same logical size (the caller validates this).\n func copySparseRegions(src, dst *os.File) (copied int64, err error) {\n \tsi, err := src.Stat()\n \tif err != nil {\n \t\treturn 0, err\n \t}\n \tsize := si.Size()\n \tsfd := int(src.Fd())\n-\tbuf := make([]byte, 1<<20)\n+\tdfd := int(dst.Fd())\n+\tbp := sparseRegionBufPool.Get().(*[]byte)\n+\tdefer sparseRegionBufPool.Put(bp)\n+\tbuf := *bp\n \toff := int64(0)\n \tfor off < size {\n \t\t// Next populated region [ds, de) in src.\n@@ -198,8 +208,27 @@\n \t\tif err != nil {\n \t\t\treturn copied, fmt.Errorf(\"SEEK_HOLE: %w\", err)\n \t\t}\n+\t\tremaining := de - ds\n+\t\tcurOff := ds\n+\n+\t\t// Attempt in-kernel zero-copy via unix.CopyFileRange where supported.\n+\t\tfor remaining > 0 {\n+\t\t\ttoCopy := remaining\n+\t\t\tif toCopy > 1<<30 {\n+\t\t\t\ttoCopy = 1 << 30\n+\t\t\t}\n+\t\t\tn, rerr := unix.CopyFileRange(sfd, &curOff, dfd, &curOff, int(toCopy), 0)\n+\t\t\tif rerr != nil {\n+\t\t\t\tbreak\n+\t\t\t}\n+\t\t\tif n == 0 {\n+\t\t\t\tbreak\n+\t\t\t}\n+\t\t\tcopied += int64(n)\n+\t\t\tremaining -= int64(n)\n+\t\t}\n+\n+\t\tif remaining > 0 {\n-\t\tif _, err := src.Seek(ds, io.SeekStart); err != nil {\n+\t\tif _, err := src.Seek(curOff, io.SeekStart); err != nil {\n \t\t\treturn copied, err\n \t\t}\n-\t\tif _, err := dst.Seek(ds, io.SeekStart); err != nil {\n+\t\tif _, err := dst.Seek(curOff, io.SeekStart); err != nil {\n \t\t\treturn copied, err\n \t\t}\n-\t\tremaining := de - ds\n \t\tfor remaining > 0 {\n \t\t\tn := int64(len(buf))\n \t\t\tif n > remaining {\n@@ -223,6 +252,7 @@\n \t\t\tremaining -= int64(r)\n \t\t}\n+\t\t}\n \t\toff = de\n \t}\n \treturn copied, nil\n"
  }
]
```
- **Expected Gain & Technical Rationale**:
  - Eliminates the 1 MiB slice allocation on every `copySparseRegions` call, reducing `composite_bytes_per_op` by ~2.1 MiB across `BenchmarkCopySparseRegions` and `BenchmarkMergeDeltaIntoBase`.
  - Enables in-kernel page-cache direct copy via `unix.CopyFileRange`, removing user-space buffer transitions and lowering CPU time spent in copy operations.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE
- **Rationale**: Validated pure Go code refactor in Subsystem B (`cmd/ateom-microvm/internal/ch/merge.go`). Eliminates per-call 1 MiB scratch buffer allocation via `sync.Pool` recycling and implements in-kernel zero-copy file range splicing via `unix.CopyFileRange` with safe streaming fallback. Concurrency and memory safety checks pass.

### 2. Safety Rubric & Checklist Grading
- **Physical Diff Audit**: PASS (Diff scoped strictly to authorized `substrate/cmd/ateom-microvm/internal/ch/merge.go`; no unauthorized structural or build script edits).
- **Deduplication Check**: PASS (First exploration of Subsystem B sparse snapshot copy/merge path; unique code refactoring).
- **Domain Trait & Concurrency Safety**: PASS (`sync.Pool` uses fixed-size byte buffer pointer recycling with proper defer put; `unix.CopyFileRange` handles partial copies and gracefully falls back on error; no goroutine leaks or unprotected shared mutations).
- **Management Cores Check**: PASS (N/A for pure Go microbenchmark).
- **Memory Headroom & OOM Guard**: PASS (Replaces per-op 1 MiB slice allocations with reusable pool).
- **Layer & Subsystem Isolation**: PASS (Subsystem B `ch` runtime layer only).
- **Infrastructure Mutation Check**: PASS (Zero infrastructure or VM mutations).

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `ch/merge.go (sync.Pool & CopyFileRange)` | `CODE_REFACTOR` | `substrate/cmd/ateom-microvm/internal/ch/merge.go` | `apo-provider-go-compiler` |
