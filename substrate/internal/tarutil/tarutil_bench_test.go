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

package tarutil

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// BenchmarkExtract simulates unpacking a rootfs overlay upper containing
// 200 files across multiple directories (typical container working set).
func BenchmarkExtract(b *testing.B) {
	srcDir := b.TempDir()
	for i := 0; i < 20; i++ {
		subDir := filepath.Join(srcDir, fmt.Sprintf("dir_%02d", i))
		if err := os.MkdirAll(subDir, 0o755); err != nil {
			b.Fatal(err)
		}
		for j := 0; j < 10; j++ {
			fpath := filepath.Join(subDir, fmt.Sprintf("file_%02d.txt", j))
			content := fmt.Sprintf("content-payload-%d-%d\n", i, j)
			if err := os.WriteFile(fpath, []byte(content), 0o644); err != nil {
				b.Fatal(err)
			}
		}
	}

	tarPath := filepath.Join(b.TempDir(), "upper.tar")
	if err := Create(context.Background(), tarPath, srcDir); err != nil {
		b.Fatalf("Create tar: %v", err)
	}

	runDir := b.TempDir()
	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		b.StopTimer()
		dstDir := filepath.Join(runDir, fmt.Sprintf("extract_%d", i))
		if err := os.MkdirAll(dstDir, 0o755); err != nil {
			b.Fatal(err)
		}
		b.StartTimer()

		if err := Extract(tarPath, dstDir); err != nil {
			b.Fatalf("Extract failed: %v", err)
		}

		b.StopTimer()
		_ = os.RemoveAll(dstDir)
		b.StartTimer()
	}
}

// BenchmarkCreate simulates archiving a rootfs overlay upper directory.
func BenchmarkCreate(b *testing.B) {
	srcDir := b.TempDir()
	for i := 0; i < 20; i++ {
		subDir := filepath.Join(srcDir, fmt.Sprintf("dir_%02d", i))
		if err := os.MkdirAll(subDir, 0o755); err != nil {
			b.Fatal(err)
		}
		for j := 0; j < 10; j++ {
			fpath := filepath.Join(subDir, fmt.Sprintf("file_%02d.txt", j))
			content := fmt.Sprintf("content-payload-%d-%d\n", i, j)
			if err := os.WriteFile(fpath, []byte(content), 0o644); err != nil {
				b.Fatal(err)
			}
		}
	}

	runDir := b.TempDir()
	ctx := context.Background()
	b.ReportAllocs()
	b.ResetTimer()

	for i := 0; i < b.N; i++ {
		b.StopTimer()
		tarPath := filepath.Join(runDir, fmt.Sprintf("out_%d.tar", i))
		b.StartTimer()

		if err := Create(ctx, tarPath, srcDir); err != nil {
			b.Fatalf("Create failed: %v", err)
		}

		b.StopTimer()
		_ = os.Remove(tarPath)
		b.StartTimer()
	}
}
