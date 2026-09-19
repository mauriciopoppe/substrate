#!/usr/bin/env python3
import sys
import os
import re
import json

def parse_bench_output(log_path, results_dir, cpu_profile="", mem_profile=""):
    """
    Parses `go test -bench` stdout/stderr.
    Example lines:
    BenchmarkMergeDeltaIntoBase-24    	      10	   6052793 ns/op	 1051024 B/op	      28 allocs/op
    BenchmarkCopySparseRegions-24     	      10	  18418926 ns/op	 1048790 B/op	       2 allocs/op
    BenchmarkReadSparseZstd-24        	      10	  36739199 ns/op	 5535944 B/op	      39 allocs/op
    BenchmarkExtract-24               	      10	  67923723 ns/op	  326857 B/op	    9538 allocs/op
    """
    bench_pattern = re.compile(
        r'^(Benchmark\w+)(?:-\d+)?\s+(\d+)\s+([\d\.]+)\s+ns/op(?:\s+([\d\.]+)\s+B/op)?(?:\s+([\d\.]+)\s+allocs/op)?'
    )
    
    benchmarks = {}
    total_ns = 0.0
    total_bytes = 0.0
    total_allocs = 0.0
    count = 0
    
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                m = bench_pattern.match(line)
                if m:
                    name = m.group(1)
                    iterations = int(m.group(2))
                    ns_per_op = float(m.group(3))
                    b_per_op = float(m.group(4)) if m.group(4) else 0.0
                    allocs_per_op = float(m.group(5)) if m.group(5) else 0.0
                    
                    benchmarks[name] = {
                        "iterations": iterations,
                        "ns_per_op": ns_per_op,
                        "bytes_per_op": b_per_op,
                        "allocs_per_op": allocs_per_op,
                    }
                    total_ns += ns_per_op
                    total_bytes += b_per_op
                    total_allocs += allocs_per_op
                    count += 1

    if count == 0:
        error_summary = {
            "status": "FAILED",
            "error": "No benchmark metrics matched in output",
            "log": log_path
        }
        with open(os.path.join(results_dir, "error.json"), "w") as f:
            json.dump(error_summary, f, indent=2)
        print("Error: No benchmark metrics parsed", file=sys.stderr)
        sys.exit(1)

    # Subsystem grouping mappings
    ch_benchmarks = ["BenchmarkMergeDeltaIntoBase", "BenchmarkCopySparseRegions"]
    ategcs_benchmarks = ["BenchmarkWriteSparseZstd", "BenchmarkReadSparseZstd"]
    tarutil_benchmarks = ["BenchmarkExtract", "BenchmarkCreate"]

    ch_ns = sum(benchmarks[b]["ns_per_op"] for b in ch_benchmarks if b in benchmarks)
    ategcs_ns = sum(benchmarks[b]["ns_per_op"] for b in ategcs_benchmarks if b in benchmarks)
    tarutil_ns = sum(benchmarks[b]["ns_per_op"] for b in tarutil_benchmarks if b in benchmarks)

    # Primary 5 metrics: Subsystem CPU latencies and Global Heap totals
    metrics = {
        "ch_ns_per_op": ch_ns,
        "ategcs_ns_per_op": ategcs_ns,
        "tarutil_ns_per_op": tarutil_ns,
        "total_bytes_per_op": total_bytes,
        "total_allocs_per_op": total_allocs,
        # Backward-compatible aliases
        "composite_ns_per_op": total_ns,
        "composite_bytes_per_op": total_bytes,
        "composite_allocs_per_op": total_allocs,
    }
    for b_name, b_data in benchmarks.items():
        metrics[f"{b_name}_ns_per_op"] = b_data["ns_per_op"]
        metrics[f"{b_name}_bytes_per_op"] = b_data["bytes_per_op"]
        metrics[f"{b_name}_allocs_per_op"] = b_data["allocs_per_op"]

    constraints = {
        "benchmark_failures": 0,
    }

    # Extract pprof hotspots if profiles exist
    profiling_summary = {}
    if cpu_profile and os.path.exists(cpu_profile):
        profiling_summary["cpu_profile"] = cpu_profile
    if mem_profile and os.path.exists(mem_profile):
        profiling_summary["mem_profile"] = mem_profile

    summary = {
        "status": "COMPLETED",
        "metrics": metrics,
        "constraints": constraints,
        "benchmarks": benchmarks,
        "profiling_summary": profiling_summary,
    }

    out_path = os.path.join(results_dir, "summary.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {out_path} successfully.")
    print(json.dumps(metrics, indent=2))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: parse_benchmark.py <log_path> <results_dir> [cpu_profile] [mem_profile]")
        sys.exit(1)
    log_file = sys.argv[1]
    res_dir = sys.argv[2]
    cpu_prof = sys.argv[3] if len(sys.argv) > 3 else ""
    mem_prof = sys.argv[4] if len(sys.argv) > 4 else ""
    parse_bench_output(log_file, res_dir, cpu_prof, mem_prof)
