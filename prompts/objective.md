---
optimization:
  backend: optuna
  metrics:
    - name: slo_max_rps
      goal: maximize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 0.5
    - name: latency_p95_ms
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 0.5
  constraints:
    - metric: http_5xx_rate
      max: 0.015
    - metric: tail_latency_mean_plus_2sigma_ms
      max: 25.0
    - metric: client_send_rate_ratio
      min: 0.90
---

# Workload Optimization Objective: Agent Substrate Ingress Routing Optimization (Go Codebase)

Optimize the Go source code of the Agent Substrate ingress data plane (`atenet-router`) to maximize sustainable request throughput under strict tail latency and reliability constraints.

## Hardware & Target Environment
- Platform: GKE cluster `substrate-test` in zone `us-west1-c` (Project `mauriciopoppe-gke-dev`).
- Machine Type: Dedicated benchmark node pool `substrate-bench-pool` with `c3-standard-44` (44 vCPUs, 180 GB RAM).
- Ingress Data Plane: Envoy proxy co-located with `atenet-router` external processor (`ext_proc`) sidecar running on Go 1.24+. Both containers pinned to 2 vCPUs.
- Upstream Workload: 50 warm Agent Substrate sandboxed actor pods (`benchmark-ateom` worker pool running `glutton` HTTP actors under gVisor).

## Empirical Baseline Metrics (Measured 2026-09-17)
- `slo_max_rps`: 5,248.0 RPS (converged over 11 adjusting stages at 100% send rate).
- `latency_p95_ms`: 18.96 ms (under the 25.0 ms SLO bound).
- `latency_p50_ms`: 3.75 ms, `latency_p99_ms`: 49.95 ms.

## Optimization Goals & Metric Definitions
1. `slo_max_rps` (Maximize): The highest sustained requests per second achieved by `atenet-router` where tail latency satisfies the SLO constraint.
2. `latency_p95_ms` (Minimize): 95th percentile end-to-end request latency measured by Nighthawk client.

## SLA Constraints
- `http_5xx_rate` <= 0.015 (at least 98.5% success rate across all trial request bursts; baseline achieved 98.78%).
- `tail_latency_mean_plus_2sigma_ms` <= 25.0 ms (tail latency upper bound per SLO).
- `client_send_rate_ratio` >= 0.90 (benchmarking client must achieve >= 90% of targeted rate without client-side saturation).

## Tuning Scope & Layer Directives

### Authorized Tuning Scope (Go Codebase & Feature Flags)
All optimization hypotheses and mutations MUST be formulated as `[ACTION: CODE_REFACTOR]` proposals containing surgical source code patches (`files: [{"filename": "...", "status": "modified", "patch": "..."}]`) compiled by `build.sh` and deployed by `run_experiment.sh`.

Allowed file scope is strictly bounded to the `atenet-router` Go codebase:
- `substrate/cmd/atenet/internal/router/ingress/resumer.go` (actor resolution and ateapi lookup lifecycle)
- `substrate/cmd/atenet/internal/router/ingress/ingress.go` (ext_proc request header processing and dispatch)
- `substrate/cmd/atenet/internal/router/ingress/parking.go` (concurrency parking lot and queueing)
- `substrate/cmd/atenet/internal/router/extproc/extproc.go` (ext_proc gRPC streaming server and bidirectional flow)
- `substrate/cmd/atenet/internal/router/extproc/metadata.go` (header manipulation and attribute extraction)
- `substrate/cmd/atenet/internal/router/cmd.go` (router CLI options and configuration plumbing)
- `substrate/cmd/atenet/internal/router/config.go` (router configuration structs and defaults)
- `substrate/cmd/atenet/internal/router/router.go` (server wiring and subsystem initialization)

### Feature Flag Workflow via `manifests/tunables.env`
To ensure safe experimentation, ablation testing, and parameter tuning, code mutations should be guarded behind feature flags:
1. **Feature Flag Guarding in Go Code**: Gate new optimization paths behind feature flags read from environment variables via `os.Getenv("FEATURE_<NAME>")` (e.g., `FEATURE_EXPERIMENTAL_PATH=true`) or configurable parameters (e.g., `FEATURE_WINDOW_SIZE=64`).
2. **Flag Declaration in `manifests/tunables.env`**: The optimizer may add, enable, disable, or tune new `FEATURE_*` flags and their associated hyperparameters in `manifests/tunables.env` using standard Optuna annotations (`# OPTUNA: name=FEATURE_..., type=categorical, choices=["true", "false"]`).
3. **Automatic Forwarding**: `run_experiment.sh` automatically syncs all `FEATURE_*` variables declared in `manifests/tunables.env` into the Kubernetes environment for the `atenet-router` container before each trial run.

### Prohibited Layers (STRICT)
- **Harness & Hardware Invariants**: Do NOT modify baseline rig parameters in `manifests/tunables.env` (`ENVOY_CONCURRENCY`, `ROUTER_GOMAXPROCS`, `ROUTER_GOGC`, `ROUTER_GOMEMLIMIT_MIB`) or Kubernetes CPU/memory requests. Tunable modifications in `manifests/tunables.env` are restricted exclusively to newly declared `FEATURE_*` flags.
- **Control Plane & Daemon Daemons**: Do NOT mutate `cmd/ateapi/`, `cmd/atelet/`, `cmd/ateom-gvisor/`, or other Substrate controllers outside `cmd/atenet/internal/router/`.
- **Harness & Benchmark Driver**: Do NOT modify the Nighthawk benchmarking harness or evaluation criteria in `substrate/benchmarking/nighthawk-ingress/`.
