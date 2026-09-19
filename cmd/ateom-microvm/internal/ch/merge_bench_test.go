//go:build linux

// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package ch

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// BenchmarkMergeDeltaIntoBase simulates a realistic 128 MiB micro-VM memory image
// with 16 MiB of populated working set in the base snapshot and 4 MiB of dirty pages
// in the delta snapshot.
func BenchmarkMergeDeltaIntoBase(b *testing.B) {
	const totalSize = 128 << 20 // 128 MiB logical size
	const pageSize = 4096

	// Base image has 16 MiB populated across multiple regions
	baseRegions := []region{
		{off: 0, data: fill(1, 1<<20)},                     // 1 MiB at start
		{off: 16 << 20, data: fill(2, 4<<20)},             // 4 MiB at 16M
		{off: 64 << 20, data: fill(3, 8<<20)},             // 8 MiB at 64M
		{off: totalSize - 3<<20, data: fill(4, 3<<20)},    // 3 MiB near end
	}

	// Delta image has 4 MiB dirty pages scattered across the address space
	deltaRegions := []region{
		{off: 512 * pageSize, data: fill(10, 512*pageSize)}, // 2 MiB overwrite
		{off: 32 << 20, data: fill(11, 1<<20)},              // 1 MiB new allocation in hole
		{off: 65 << 20, data: fill(12, 1<<20)},              // 1 MiB overwrite inside 64M block
	}

	ctx := context.Background()

	// Pre-create the template images so we can clone them quickly per iteration
	templateDir := b.TempDir()
	baseTmpl := filepath.Join(templateDir, "base.tmpl")
	deltaTmpl := filepath.Join(templateDir, "delta.tmpl")
	writeSparseTmpl(b, baseTmpl, totalSize, baseRegions)
	writeSparseTmpl(b, deltaTmpl, totalSize, deltaRegions)

	runDir := b.TempDir()
	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		b.StopTimer()
		basePath := filepath.Join(runDir, "base.bin")
		deltaPath := filepath.Join(runDir, "delta.bin")
		cloneFile(b, baseTmpl, basePath)
		cloneFile(b, deltaTmpl, deltaPath)
		b.StartTimer()

		if err := MergeDeltaIntoBase(ctx, basePath, deltaPath); err != nil {
			b.Fatalf("MergeDeltaIntoBase failed: %v", err)
		}

		b.StopTimer()
		_ = os.Remove(deltaPath)
		b.StartTimer()
	}
}

// BenchmarkCopySparseRegions directly benchmarks copySparseRegions between two files
// without rename overhead.
func BenchmarkCopySparseRegions(b *testing.B) {
	const totalSize = 128 << 20
	deltaRegions := []region{
		{off: 1 << 20, data: fill(10, 4<<20)},  // 4 MiB
		{off: 32 << 20, data: fill(11, 8<<20)}, // 8 MiB
		{off: 80 << 20, data: fill(12, 4<<20)}, // 4 MiB
	}

	templateDir := b.TempDir()
	deltaTmpl := filepath.Join(templateDir, "delta.tmpl")
	dstTmpl := filepath.Join(templateDir, "dst.tmpl")
	writeSparseTmpl(b, deltaTmpl, totalSize, deltaRegions)
	writeSparseTmpl(b, dstTmpl, totalSize, nil) // All holes

	runDir := b.TempDir()
	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		b.StopTimer()
		srcPath := filepath.Join(runDir, "src.bin")
		dstPath := filepath.Join(runDir, "dst.bin")
		cloneFile(b, deltaTmpl, srcPath)
		cloneFile(b, dstTmpl, dstPath)

		src, err := os.Open(srcPath)
		if err != nil {
			b.Fatal(err)
		}
		dst, err := os.OpenFile(dstPath, os.O_RDWR, 0o600)
		if err != nil {
			src.Close()
			b.Fatal(err)
		}
		b.StartTimer()

		_, err = copySparseRegions(src, dst)
		if err != nil {
			src.Close()
			dst.Close()
			b.Fatalf("copySparseRegions: %v", err)
		}

		b.StopTimer()
		src.Close()
		dst.Close()
		_ = os.Remove(srcPath)
		_ = os.Remove(dstPath)
		b.StartTimer()
	}
}

func writeSparseTmpl(tb testing.TB, path string, size int64, regions []region) {
	tb.Helper()
	f, err := os.Create(path)
	if err != nil {
		tb.Fatal(err)
	}
	defer f.Close()
	if err := f.Truncate(size); err != nil {
		tb.Fatal(err)
	}
	for _, r := range regions {
		if _, err := f.WriteAt(r.data, r.off); err != nil {
			tb.Fatal(err)
		}
	}
	if err := f.Sync(); err != nil {
		tb.Fatal(err)
	}
}

func cloneFile(tb testing.TB, srcPath, dstPath string) {
	tb.Helper()
	s, err := os.Open(srcPath)
	if err != nil {
		tb.Fatal(err)
	}
	defer s.Close()
	si, err := s.Stat()
	if err != nil {
		tb.Fatal(err)
	}
	d, err := os.OpenFile(dstPath, os.O_RDWR|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		tb.Fatal(err)
	}
	defer d.Close()
	if err := d.Truncate(si.Size()); err != nil {
		tb.Fatal(err)
	}
	// Fast sparse clone using copySparseRegions or simple read
	_, _ = copySparseRegions(s, d)
}
