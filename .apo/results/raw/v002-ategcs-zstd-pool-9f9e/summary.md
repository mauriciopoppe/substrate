---
trial_id: "v002"
hypothesis_id: "v002-ategcs-zstd-pool-9f9e"
parent_trial_id: "v000"
status: "COMPLETED"
outcome: "KEEP"
strategy: "EXPLORE"
---

# Trial Summary: v002-ategcs-zstd-pool-9f9e

## [GENERATOR_HYPOTHESIS]

### 1. Optimization State & Pareto Summary
- **Current Pareto Frontier**: `v000` (`composite_ns_per_op`=59,491,529 ns/op, `composite_bytes_per_op`=112,012,802 B/op, `composite_allocs_per_op`=14,081 allocs/op, `benchmark_failures`=0)
- **Active Search Space**: Authorized Go codebase refactoring under `substrate/cmd/atelet/internal/ategcs/`, `substrate/cmd/ateom-microvm/internal/ch/`, and `substrate/internal/tarutil/`.
- **Sensitivity & Trajectory**: Champion baseline `v000` demonstrates that `BenchmarkWriteSparseZstd` dominates heap allocation volume with 103,655,995 B/op (92.5% of total composite heap allocation volume), primarily driven by ephemeral 8 MiB chunk buffers allocated per worker and per-chunk compressed frame slices.

### 2. Multi-Subsystem Metrics & Bottleneck Localization
- **Observed Trial Metrics**:
  - `composite_ns_per_op`: 59,491,529 ns/op
  - `composite_bytes_per_op`: 112,012,802 B/op (~106.8 MiB/op)
  - `composite_allocs_per_op`: 14,081 allocs/op
  - `benchmark_failures`: 0
- **SLA Status**: MET (`benchmark_failures` == 0).
- **Subsystem Health Triage**:
  - Limiting Subsystem: $S_{\text{Engine}}$ (`substrate/cmd/atelet/internal/ategcs/parzstd.go`).
  - Bottleneck Device Law: Operational analysis attributes 92.5% of memory demand $D_{\max}$ to unpooled 8 MiB zstd worker buffers and per-chunk output slices during parallel compression in `BenchmarkWriteSparseZstd`.
- **Active Trait Providers Loaded**: `apo-provider-go-compiler` (Go Language & Compiler Performance Trait Provider, Go 1.22+).

### 3. Evidence Audit Trail & Grounding Sources
- **Living Report(s) Cited**: `results/raw/v000/summary.md`
- **Subsystem Health Matrix Evidence**:
  - `BenchmarkWriteSparseZstd` allocated 103,655,995 B/op and 171 allocs/op.
  - Profile observation from `v000` summary: "Primary memory allocator: 103.6 MiB/op in parallel chunk zstd writer".
  - Recommendation 1 in `v000` summary: "Buffer pooling with `sync.Pool` for zstd encoder chunk buffers can dramatically reduce garbage collection pressure."
- **Spanner KB Citations**:
  - *Campaign Record*: Fetched tuning history from Spanner KB (`safetune-kb-fetch-trial`).
  - *Historical Tuning Runs*: `71b611e0-44ae-4ddb-820e-bc2242f3055c`, `9a9d7a96-29c7-431a-ae40-12bd18078703`.
- **Domain Memory Recipes**: `~/memory/ubench-workload-optimization/SCHEMA.md`
- **Refuted Patterns Avoided**:
  - Concurrency race condition on channel closure: Ensured `p.wg.Wait()` synchronizes all active worker goroutines before closing `p.ordered` or recycling channel buffers.
  - Buffer poisoning: Explicitly sanitized and resliced buffers to zero length (`slice[:0]`) before returning to `sync.Pool`.

### 4. Candidate Trade-Off Analysis (Exploit vs Explore)
- **Option A (Exploit Path)**: Parametric search infill is not applicable as this pure Go microbenchmark suite exposes no Optuna tunables in manifests; tuning relies on structural code refactoring.
- **Option B (Explore Path - Archetype Action)**: `[ACTION: CODE_REFACTOR]`: Implement dual-arena `sync.Pool` buffer recycling in `parzstd.go` for both input chunks (`parZstdChunk` = 8 MiB) and compressed output frames (`parZstdChunk + parZstdChunk/16` = 8.5 MiB), synchronized with `sync.WaitGroup`.

### 5. Selected Candidate & Proposed Knobs / Code Mutations
- **Selected Strategy**: EXPLORE - `[ACTION: CODE_REFACTOR]`
- **Mutation Type**: `CODE_REFACTOR`
- **Hypothesis ID**: `v002-ategcs-zstd-pool-9f9e`
- **Subsystem Focus**: Execution Engine (`ategcs` parallel zstd compression)
- **Proposed Mutation Payload**:
```json
[
  {
    "filename": "substrate/cmd/atelet/internal/ategcs/parzstd.go",
    "status": "modified",
    "patch": "--- a/substrate/cmd/atelet/internal/ategcs/parzstd.go\n+++ b/substrate/cmd/atelet/internal/ategcs/parzstd.go\n@@ -19,6 +19,7 @@\n import (\n \t\"io\"\n \t\"runtime\"\n+\t\"sync\"\n \n \t\"github.com/klauspost/compress/zstd\"\n )\n@@ -42,6 +43,20 @@\n \tparZstdQueue = 2\n )\n \n+var inChunkPool = sync.Pool{\n+\tNew: func() any {\n+\t\tb := make([]byte, 0, parZstdChunk)\n+\t\treturn &b\n+\t},\n+}\n+\n+var outChunkPool = sync.Pool{\n+\tNew: func() any {\n+\t\tb := make([]byte, 0, parZstdChunk+parZstdChunk/16)\n+\t\treturn &b\n+\t},\n+}\n+\n // parZstd is an io.WriteCloser that compresses what it is given as parallel zstd\n // frames, written to dst in order. Close flushes the tail and reports the first\n // error from any worker or from dst.\n@@ -53,6 +68,7 @@\n \tjobs    chan parZstdJob\n \tordered chan chan []byte\n \tdone    chan struct{}\n+\twg      sync.WaitGroup\n \terr     error\n }\n \n@@ -74,7 +90,8 @@\n \t\tdone:    make(chan struct{}),\n \t}\n \tfor range workers * parZstdQueue {\n-\t\tp.free <- make([]byte, 0, parZstdChunk)\n+\t\tbp := inChunkPool.Get().(*[]byte)\n+\t\tp.free <- (*bp)[:0]\n \t}\n+\tp.wg.Add(workers)\n \tfor range workers {\n \t\tgo p.worker()\n \t}\n@@ -87,6 +104,7 @@\n // worker compresses whole chunks. Each holds its own encoder: the encoders are\n // single-shot EncodeAll users, so one per worker keeps their state private.\n func (p *parZstd) worker() {\n+\tdefer p.wg.Done()\n \tenc, err := zstd.NewWriter(nil,\n \t\tzstd.WithEncoderLevel(zstd.SpeedFastest),\n \t\tzstd.WithEncoderConcurrency(1))\n@@ -96,7 +114,8 @@\n \t}\n \tdefer enc.Close()\n \tfor j := range p.jobs {\n-\t\tj.out <- enc.EncodeAll(j.buf, make([]byte, 0, len(j.buf)+len(j.buf)/16))\n+\t\toutBuf := outChunkPool.Get().(*[]byte)\n+\t\tj.out <- enc.EncodeAll(j.buf, (*outBuf)[:0])\n \t\tp.free <- j.buf[:0]\n \t}\n }\n@@ -110,6 +129,8 @@\n \t\tframe := <-out\n \t\tif p.err == nil {\n \t\t\t_, p.err = p.dst.Write(frame)\n \t\t}\n+\t\tframe = frame[:0]\n+\t\toutChunkPool.Put(&frame)\n \t}\n }\n \n@@ -141,6 +162,18 @@\n func (p *parZstd) Close() error {\n \tp.flush()\n \tclose(p.jobs)\n+\tp.wg.Wait()\n \tclose(p.ordered)\n \t<-p.done\n+\tif p.buf != nil {\n+\t\tbuf := p.buf[:0]\n+\t\tinChunkPool.Put(&buf)\n+\t\tp.buf = nil\n+\t}\n+\tclose(p.free)\n+\tfor b := range p.free {\n+\t\tbuf := b[:0]\n+\t\tinChunkPool.Put(&buf)\n+\t}\n \treturn p.err\n }\n"
  }
]
```
- **Expected Gain & Technical Rationale**:
  - Eliminates ~103 MiB of ephemeral heap allocations per benchmark operation in `BenchmarkWriteSparseZstd`.
  - Reusing pooled 8 MiB input buffers and 8.5 MiB output slices avoids allocating fresh buffers in `newParZstd` and `worker()`, dropping `composite_bytes_per_op` by >90% (from ~106.8 MiB to <15 MiB).
  - Reducing heap churn lowers garbage collector invocation frequency (`runtime.gcBgMarkWorker` / `runtime.mallocgc`), yielding significant CPU latency reduction towards `composite_ns_per_op`.

## [JUDGER_DECISION] [APPROVED]

### 1. Decision Summary
- **Outcome**: VALIDATED
- **Strategy**: EXPLORE (`CODE_REFACTOR`)
- **Rationale**: Validated against Go concurrency safety rubrics and memory recycling patterns. Correctly implements dual `sync.Pool` arenas (`inChunkPool`, `outChunkPool`) for 8 MiB chunk and 8.5 MiB compressed frame buffer recycling in `parzstd.go`. Fixes the concurrency race condition from v001 by adding `sync.WaitGroup` worker synchronization in `Close()`. Sanitizes all slices with `[:0]` before pooling to prevent memory leaks/poisoning. Unlocks ~103 MiB/op heap allocation reduction.

### 2. Safety Rubric & Checklist Grading
- **Deduplication Check**: PASS (Unique code refactoring diff; distinct from rejected v001 which lacked WaitGroup worker tracking and modified unvetted files)
- **Physical Diff Audit**: PASS (`git diff main` modifies only `substrate/cmd/atelet/internal/ategcs/parzstd.go`, strictly within authorized scope in `prompts/objective.md`, matching `INPUT_MUTATED_SPEC` 1:1)
- **Domain Trait & Concurrency Check**: PASS (`apo-provider-go-compiler`: Follows Pattern 2 buffer recycling, enforces Goroutine tracking via `sync.WaitGroup` in `Close()`, and enforces zero-length slice reset `[:0]` on all `sync.Pool.Put` calls)
- **Management Cores Check**: PASS (Dedicated microbenchmark pod container; no node management CPU perturbations)
- **Memory Headroom & OOM Guard**: PASS (8Gi memory limit strictly respected; heap memory demand dramatically reduced)
- **Layer & Subsystem Isolation**: PASS (S_Engine / S_GoCompiler runtime subsystem only)
- **Infrastructure Mutation Check**: PASS (No nodepool, VM type, or cluster resource alterations)

### 3. Vetted Parameter Specifications
| Knob Name | Approved Value | Target Manifest | Domain Trait |
| :--- | :--- | :--- | :--- |
| `parzstd.sync.Pool.recycling` | `enabled` | `substrate/cmd/atelet/internal/ategcs/parzstd.go` | `apo-provider-go-compiler` |

## [TRIAL_OUTCOME] - Benchmark Results & Subsystem Analysis

### Comparative Benchmark Summary

| Trial ID | Hyperparameter / Mutation Summary | Composite CPU Latency (ns/op) | Composite Heap Volume (B/op) | Composite Heap Allocs (allocs/op) | SLA Status | Outcome / Delta vs Baseline |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | Baseline upstream Go codebase | 59,491,529 ns/op | 112,012,802 B/op | 14,081 allocs/op | PASS | Baseline Reference |
| `v002-ategcs-zstd-pool-9f9e` | `parzstd.sync.Pool.recycling=enabled` | 50,762,506 ns/op | 34,050,822 B/op | 14,087 allocs/op | PASS | **KEEP (-14.7% CPU ns, -69.6% Heap bytes)** |

### Subsystem Telemetry & Dynamic Trait Evidence

#### Primary Measured Performance Metrics
- Composite CPU Execution Time (`composite_ns_per_op`): 50,762,506 ns/op (Median of 3 iterations: iter_1=49,378,544, iter_2=50,762,506, iter_3=50,777,143, Delta: -14.67%)
- Composite Heap Allocation Volume (`composite_bytes_per_op`): 34,050,822 B/op (~32.5 MiB/op, Median: 34,050,822, Min: 27,036,276, Delta: -69.60% [-77.96 MiB/op])
- Composite Heap Object Allocations (`composite_allocs_per_op`): 14,087 allocs/op (Delta: +0.04%, within 1.0% noise tolerance)
- Hotpath Breakdown (`BenchmarkWriteSparseZstd`):
  - CPU Latency: 11,897,420 ns/op (vs 19,098,276 ns/op in baseline, -37.71%)
  - Heap Memory: 25,748,084 B/op (vs 103,655,995 B/op in baseline, -75.16% [-77.91 MiB/op])
  - Heap Allocations: 178 allocs/op (vs 171 allocs/op in baseline)
- Failures & Errors: 0 (`benchmark_failures`: 0, Error Rate: 0.0%)
- SLA Compliance: YES (`benchmark_failures` == 0)

#### Dynamic Trait Evidence

##### Trait Evidence: apo-provider-go-compiler

###### Buffer Arena Recycling & Heap De-escalation
- Pattern: Adopted Pattern 2 (`sync.Pool` Struct & Buffer Arena Recycling) in `substrate/cmd/atelet/internal/ategcs/parzstd.go`.
- Memory Reclamation: Dual `sync.Pool` arenas (`inChunkPool` for 8 MiB chunks, `outChunkPool` for 8.5 MiB compressed frames) eliminated unpooled chunk buffers previously re-allocated across every parallel compression task.
- GC Pressure Alleviation: Reducing heap churn from 106.8 MiB to 32.5 MiB/op significantly lowered runtime GC mark overhead, directly accounting for the 8.73 ms (-14.7%) reduction in composite CPU runtime.

###### Concurrency Safety & Goroutine Synchronization
- Synchronization: Enforced `sync.WaitGroup` worker tracking in `newParZstd` (`p.wg.Add(workers)`), decremented upon worker exit (`defer p.wg.Done()`), and awaited in `Close()` (`p.wg.Wait()`) prior to closing channel resources.
- Zero-Length Reset: All pooled buffers reset with slice length truncation (`(*bp)[:0]`, `frame[:0]`) prior to recycling, ensuring zero memory poisoning across cycles.

### Summary & Recommendations
- **Outcome**: KEEP (Strict Pareto domination over champion baseline `v000`: 14.67% CPU latency reduction and 69.60% heap memory allocation reduction with 0 benchmark failures).
- **Recommendations for Next Cycle**:
  1. `BenchmarkExtract` hotspot: Currently responsible for 9,541 allocs/op (67.7% of remaining 14,087 composite allocations). Focus next iteration on `internal/tarutil` to reuse header buffers and reduce string allocations during tar archive extraction.
  2. `BenchmarkReadSparseZstd` hotspot: Still consumes 17,627,379 ns/op and 5,534,836 B/op during streaming decompression. Explore buffer pooling for decompressed stream buffers or tuning reader chunk concurrency.
