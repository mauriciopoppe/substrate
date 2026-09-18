---
optimization:
  backend: optuna
  metrics:
    - name: resume_actor_p95_ms
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 1.0
    - name: read_ram_after_resume_p95_ms
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 1.0
    - name: suspend_actor_p95_ms
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 1.0
  constraints:
    - metric: error_rate
      max: 0.001
    - metric: node_oom_events
      max: 0
    - metric: client_send_rate_ratio
      min: 0.90
---

# Workload Optimization Objective: Substrate Micro-VM Memory & Checkpoint Optimization (Go Codebase)

Optimize the Go source code of the Agent Substrate micro-VM runtime (`ateom-microvm`) and node supervisor (`atelet`) to minimize actor resume latency, post-resume page fault read latency, and suspend latency under strict reliability constraints.

## Target Hardware & Workload
- Platform: GKE cluster `substrate-test-2` in zone `us-west1-c` (Project `mauriciopoppe-gke-dev`).
- Machine Type: `c3-standard-44` (nested virtualization / KVM enabled).
- Workload: `glutton_mem_1gi_microvm` running under Cloud-Hypervisor micro-VMs.

## Optimization Goals
1. `resume_actor_p95_ms` (Minimize): Time required to restore and unpause a 1 GiB micro-VM actor.
2. `read_ram_after_resume_p95_ms` (Minimize): Time required to traverse all resident pages after resume under demand paging.
3. `suspend_actor_p95_ms` (Minimize): Time to pause, snapshot, and persist the actor memory state.

## Constraints
- `error_rate` <= 0.001 (99.9% success rate across all gRPC and HTTP operations).
- `node_oom_events` == 0 (zero host kernel or cgroup OOM killer activations).
- `client_send_rate_ratio` >= 0.90 (no client-side stalls).

## Authorized Code Refactoring Scope
Mutations must be formulated as `[ACTION: CODE_REFACTOR]` proposals containing surgical source code patches across:
- `substrate/cmd/ateom-microvm/` (Micro-VM sandbox service, CH client, restore, checkpoint, overlay, prefault)
- `substrate/cmd/atelet/` (Node supervisor, snapshot download/upload, GCS client, bundle prep)

## Hypothesis-Driven Parameter & Feature Workflow
Feature flags and parameter knobs are not pre-configured. The APO reasoning engine is responsible for hypothesizing, declaring, and tuning new flags or hyperparameters within `manifests/tunables.env` (using `# OPTUNA:` annotations) as needed for its proposed refactors.
All variables in `manifests/tunables.env` prefixed with `FEATURE_*` are automatically propagated to the Kubernetes runtime environment before each trial.

