# Unified Historical Ledger

## [2026-09-16T21:30:00Z] [INITIALIZATION]

Initialized the Agent Substrate ingress routing optimization workspace conforming to the APO 3-Component Architecture and WorkQueue execution contracts.
- Objective: Maximize `slo_max_rps` under 25ms tail latency SLO and 99.9% success rate.
- Workload Directory: `/usr/local/google/home/mauriciopoppe/go/src/user.git.corp.google.com/mauriciopoppe/gke-workload-perf/substrate-ingress-tuning`.
- Target Stack: GKE cluster `substrate-test` (zone `us-west1-c`, machine type `c3-standard-4`).
- Initial baseline calibration trial (`v000`).

| Trial ID | Baseline | Mutated Parameters | Key Metrics | Outcome | Living Report Pointer |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `v000` | (Initial) | Baseline defaults (`ENVOY_CONCURRENCY=2, ROUTER_GOMAXPROCS=2, ROUTER_GOGC=200, ROUTER_GOMEMLIMIT_MIB=1024`) | `slo_max_rps`=5248.0 RPS, `latency_p95_ms`=18.96 ms | **KEEP** (Champion) | `results/raw/v000/summary.md` |
