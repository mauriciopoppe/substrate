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

package ategcs

import (
	"bytes"
	"io"
	"os"
	"path/filepath"
	"testing"
)

// BenchmarkWriteSparseZstd benchmarks encoding sparse extents into a zstd stream.
func BenchmarkWriteSparseZstd(b *testing.B) {
	const totalSize = 128 << 20
	regions := []region{
		{off: 0, len: 1 << 20, fill: 0x11},
		{off: 16 << 20, len: 4 << 20, fill: 0x22},
		{off: 64 << 20, len: 8 << 20, fill: 0x33},
		{off: totalSize - 3<<20, len: 3 << 20, fill: 0x44},
	}

	dir := b.TempDir()
	srcPath := filepath.Join(dir, "sparse_src.bin")
	writeSparseSourceTB(b, srcPath, totalSize, regions)

	src, err := os.Open(srcPath)
	if err != nil {
		b.Fatal(err)
	}
	defer src.Close()

	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		b.StopTimer()
		if _, err := src.Seek(0, io.SeekStart); err != nil {
			b.Fatal(err)
		}
		var buf bytes.Buffer
		b.StartTimer()

		_, _, err := writeSparseZstd(&buf, src)
		if err != nil {
			b.Fatalf("writeSparseZstd failed: %v", err)
		}
	}
}

// BenchmarkReadSparseZstd benchmarks decoding the sparse-extent stream to a sparse file.
func BenchmarkReadSparseZstd(b *testing.B) {
	const totalSize = 128 << 20
	regions := []region{
		{off: 0, len: 1 << 20, fill: 0x11},
		{off: 16 << 20, len: 4 << 20, fill: 0x22},
		{off: 64 << 20, len: 8 << 20, fill: 0x33},
		{off: totalSize - 3<<20, len: 3 << 20, fill: 0x44},
	}

	dir := b.TempDir()
	srcPath := filepath.Join(dir, "sparse_src.bin")
	writeSparseSourceTB(b, srcPath, totalSize, regions)

	src, err := os.Open(srcPath)
	if err != nil {
		b.Fatal(err)
	}
	defer src.Close()

	var streamBuf bytes.Buffer
	_, _, err = writeSparseZstd(&streamBuf, src)
	if err != nil {
		b.Fatalf("prep writeSparseZstd: %v", err)
	}
	streamBytes := streamBuf.Bytes()
	payload := streamBytes[len(sparseMagic):]

	runDir := b.TempDir()
	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		b.StopTimer()
		dstPath := filepath.Join(runDir, "sparse_dst.bin")
		dst, err := os.Create(dstPath)
		if err != nil {
			b.Fatal(err)
		}
		reader := bytes.NewReader(payload)
		b.StartTimer()

		_, err = readSparseZstd(dst, reader)
		if err != nil {
			dst.Close()
			b.Fatalf("readSparseZstd: %v", err)
		}

		b.StopTimer()
		dst.Close()
		_ = os.Remove(dstPath)
		b.StartTimer()
	}
}

func writeSparseSourceTB(tb testing.TB, path string, size int64, regions []region) {
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
		buf := make([]byte, r.len)
		for i := range buf {
			buf[i] = r.fill
		}
		if _, err := f.WriteAt(buf, r.off); err != nil {
			tb.Fatal(err)
		}
	}
	if err := f.Sync(); err != nil {
		tb.Fatal(err)
	}
}
