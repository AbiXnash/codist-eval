// changed prints the methods a fix changed: for each line the diff adds or removes, the method
// that contains it in the version it belongs to. Output: one "pkg.Class#method" per line.
package main

import (
	"bufio"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"github.com/AbiXnash/codist-java"
)

var hunk = regexp.MustCompile(`^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@`)

func main() {
	repo, sha, oldDir, newDir := os.Args[1], os.Args[2], os.Args[3], os.Args[4]
	files, _ := exec.Command("git", "-C", repo, "diff", "--name-only", sha+"~1", sha, "--", "*.java", ":!*src/test*").Output()
	out := map[string]bool{}
	sc := bufio.NewScanner(bytesReader(files))
	for sc.Scan() {
		path := sc.Text()
		diff, _ := exec.Command("git", "-C", repo, "diff", "-U0", sha+"~1", sha, "--", path).Output()
		var oldLines, newLines []int
		ds := bufio.NewScanner(bytesReader(diff))
		o, n := 0, 0
		for ds.Scan() {
			l := ds.Text()
			if m := hunk.FindStringSubmatch(l); m != nil {
				o, _ = strconv.Atoi(m[1])
				n, _ = strconv.Atoi(m[3])
				continue
			}
			switch {
			case len(l) > 0 && l[0] == '-' && !hasPrefix(l, "---"):
				oldLines = append(oldLines, o)
				o++
			case len(l) > 0 && l[0] == '+' && !hasPrefix(l, "+++"):
				newLines = append(newLines, n)
				n++
			}
		}
		mark(out, oldDir+"/"+path, path, oldLines)
		mark(out, newDir+"/"+path, path, newLines)
	}
	for _, c := range callers(newDir, out) {
		out[c] = true
	}
	keys := make([]string, 0, len(out))
	for k := range out {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		fmt.Println(k)
	}
}

func mark(out map[string]bool, file, path string, lines []int) {
	src, err := os.ReadFile(file)
	if err != nil {
		return
	}
	ix := java.Build(map[string][]byte{path: src}, nil)
	for _, l := range lines {
		t, m := ix.TypeAt(path, l)
		if t == nil {
			continue
		}
		id := binaryName(t, ix)
		if m != nil {
			out[id+"#"+m.Name] = true
		} else {
			out[id+"#<field>"] = true
		}
	}
}

// binaryName is the name the JVM knows a class by: nested classes join with $.
func binaryName(t *java.Type, ix *java.Index) string {
	name := t.ID
	for _, o := range ix.Types {
		if o != t && len(t.ID) > len(o.ID) && t.ID[:len(o.ID)+1] == o.ID+"." {
			name = o.ID + "$" + t.ID[len(o.ID)+1:]
		}
	}
	return name
}

// callers lists the methods in the new version that call a changed method, found with Codist's call
// graph: the bug may only show when the changed method is reached the way the project reaches it.
func callers(dir string, changed map[string]bool) []string {
	sources := map[string][]byte{}
	filepath.WalkDir(dir, func(p string, d fs.DirEntry, err error) error {
		if err == nil && !d.IsDir() && strings.HasSuffix(p, ".java") && !strings.Contains(p, "/src/test/") {
			src, _ := os.ReadFile(p)
			sources[strings.TrimPrefix(p, dir+"/")] = src
		}
		return nil
	})
	ix := java.Build(sources, nil)
	byFile := map[string]*java.Type{}
	name := func(file, class string) string {
		for _, t := range ix.Types {
			if t.File == file && t.Name == class {
				return binaryName(t, ix)
			}
		}
		return ""
	}
	_ = byFile
	var out []string
	for _, c := range java.BuildCallGraph(sources, ix.Types).Calls() {
		to := name(c.To.File, c.To.Class) + "#" + c.To.Name
		if changed[to] && !c.From.Test {
			if from := name(c.From.File, c.From.Class); from != "" {
				out = append(out, from+"#"+c.From.Name)
			}
		}
	}
	return out
}

func hasPrefix(s, p string) bool { return len(s) >= len(p) && s[:len(p)] == p }

type reader struct{ b []byte }

func (r *reader) Read(p []byte) (int, error) {
	if len(r.b) == 0 {
		return 0, fmt.Errorf("EOF")
	}
	n := copy(p, r.b)
	r.b = r.b[n:]
	return n, nil
}
func bytesReader(b []byte) *reader { return &reader{b} }
