# Unified Historical Ledger

## [2026-09-17T21:05:00Z] [INITIALIZATION]

Initialized the Agent Substrate Study 1 (Micro-VM Actor Checkpoint/Restore & Memory Demand-Paging) optimization workspace conforming to the APO 3-Component Architecture and WorkQueue execution contracts.
- Objective: Minimize `resume_actor_p95_ms`, `read_ram_after_resume_p95_ms`, and `suspend_actor_p95_ms` under zero errors and zero OOM events.
- Workload Directory: `/usr/local/google/home/mauriciopoppe/go/src/user.git.corp.google.com/mauriciopoppe/gke-workload-perf/substrate-memory-and-checkpoint`.
- Target Stack: GKE cluster `substrate-test-2` (zone `us-west1-c`, node pool `substrate-bench-pool`, machine type `c3-standard-44`, nested virtualization enabled).
- Runtime: Micro-VM (`ateom-microvm` with Cloud Hypervisor and virtiofsd).
- Workload: `glutton_mem_1gi_microvm` (1 GiB memory working set, 64 MiB churn).
- Initial baseline calibration trial (`v000`).

| Trial ID | Baseline | Mutated Parameters | Key Metrics | Outcome | Living Report Pointer |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | (Initial) | Baseline defaults (`SANDBOX_CLASS="microvm"`, `ACTOR_MEMORY="1536Mi"`, `MEM_TARGET="1Gi"`, `MEM_CHURN="64Mi"`) | `read_ram_p95`=3400.0 ms (0.0% variance across 3 runs), `resume_p95`=3833.3 ms (mean), `suspend_p95`=3766.7 ms (mean), `error_rate`=0.0% | **KEEP** (Champion Baseline) | `BASELINE.md`, `results/baseline/`, `results/baseline_run2/`, `results/baseline_run3/` |
