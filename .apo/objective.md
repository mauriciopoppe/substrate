---
optimization:
  backend: optuna
  metrics:
    - name: ttfi_p90_ms
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 0.1
    - name: ttfi_p95_ms
      goal: minimize
      min_improvement_pct: 5.0
      noise_tolerance_pct: 0.1
    - name: suspend_actor_p95_ms
      goal: minimize
      min_improvement_pct: 2.0
      noise_tolerance_pct: 0.1
  constraints:
    - metric: error_rate
      max: 0.001
    - metric: node_oom_events
      max: 0
    - metric: client_send_rate_ratio
      min: 0.90
  allowed_file_scope: |
    cmd/atelet/**
    cmd/atenet/**
    internal/atelet/**
    internal/atenet/**
    internal/benchmarking/**
    .apo/manifests/**
---

# Objective: E2E Time To First Instruction (TTFI) Under 100ms P90

## Target
Reduce end-to-end suspend/resume latency (Time To First Instruction) for sleeping agent sandboxes to **< 100ms P90** under realistic memory working sets.

## Workload Profile
- **Runtime Substrate**: gVisor (Phase 1 calibration and fast iteration floor) followed by MicroVM (`ateom-microvm`, Phase 2).
- **Resident State**: 512 MiB populated resident memory (`/fill_ram`).
- **First Read Working Set**: 64 MiB first-read slice (`POST /readram`), representing immediate startup code & context ingestion.
- **Memory Churn**: 64 MiB in-place dirtying (`/churn_ram`) during active execution.
- **Lifecycle & Traffic**:
  - Implicit resume mode (`--resume-mode implicit`): The client does NOT invoke explicit gRPC `ResumeActor`. Traffic sent through Envoy/atenet triggers the ext_proc wake sequence transparently.
  - Duration: 2 minutes.
  - Concurrency: 1 VU for `v000` baseline noise-free floor calibration; 5-10 VUs for contention scaling.

## Primary Metric
- `ttfi_p90_ms`: The 90th percentile roundtrip latency of `GluttonReadRAM` (which includes ingress buffering, ext_proc wake, state restoration, and HTTP response delivery).
