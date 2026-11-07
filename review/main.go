// review measures what Codist's review finds on real bugs, with and without an option, on the same bugs.
//
// For each bug it checks out the fixed commit, commits the bug back in (the fix reversed, main code only), and
// reviews that commit once per variant. A finding within 3 lines of a line the bug commit adds counts as located:
// an upper bound, since a finding near the bug may not name it, so read the located findings before quoting them.
//
//	go run ./review -model qwen2.5-coder:7b -out results.json ../behaviour/bugs.txt
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	git "github.com/AbiXnash/codist-git"
	model "github.com/AbiXnash/codist-model"
	review "github.com/AbiXnash/codist-review"
	"github.com/AbiXnash/codist-review/store"
)

const locate = 3

type finding struct {
	Path, Title, Source string
	Line                int
	Located             bool
}

type variant struct {
	Findings []finding
	Located  int
	Took     float64
	Error    string `json:",omitempty"`
}

type result struct {
	Bug      string
	Without  variant
	With     variant
	Targets  map[string][]int
	Problems string `json:",omitempty"`
}

func main() {
	name := flag.String("model", "qwen2.5-coder:7b", "model on the server")
	url := flag.String("url", "http://localhost:11434", "model server")
	out := flag.String("out", "review-results.json", "where to write results")
	cache := flag.String("cache", filepath.Join(os.Getenv("HOME"), ".cache/codist-bench/repos"), "benchmark clones")
	flag.Parse()
	list, err := os.ReadFile(flag.Arg(0))
	if err != nil {
		fail(err)
	}
	client := model.New(*url, *name, 8192)
	if ok, note := client.Status(context.Background()); !ok {
		fail(fmt.Errorf("%s", note))
	}
	var results []result
	for _, line := range strings.Split(strings.TrimSpace(string(list)), "\n") {
		f := strings.Fields(line)
		if len(f) < 3 {
			continue
		}
		res := runBug(f[0], filepath.Join(*cache, f[1]), f[2], client)
		results = append(results, res)
		fmt.Printf("%-45s without %d/%d  with %d/%d  %s\n", res.Bug, res.Without.Located, len(res.Without.Findings),
			res.With.Located, len(res.With.Findings), res.Problems)
		b, _ := json.MarshalIndent(results, "", " ")
		_ = os.WriteFile(*out, b, 0o644)
	}
	without, with := 0, 0
	for _, r := range results {
		if r.Without.Located > 0 {
			without++
		}
		if r.With.Located > 0 {
			with++
		}
	}
	fmt.Printf("\nbugs located: without callers %d of %d, with callers %d of %d\n", without, len(results), with, len(results))
}

func runBug(bug, cached, fixed string, client *model.Client) result {
	res := result{Bug: bug}
	work, _ := os.MkdirTemp("", "codist-review-"+bug)
	defer os.RemoveAll(work)
	tree := filepath.Join(work, "tree")
	gitIn := func(dir string, args ...string) (string, error) {
		cmd := exec.Command("git", append([]string{"-C", dir, "-c", "user.name=Eval", "-c", "user.email=eval@codist", "-c", "commit.gpgsign=false"}, args...)...)
		b, err := cmd.CombinedOutput()
		return strings.TrimSpace(string(b)), err
	}
	if msg, err := gitIn(cached, "worktree", "add", "-q", "--detach", tree, fixed); err != nil {
		res.Problems = "checkout: " + msg
		return res
	}
	defer gitIn(cached, "worktree", "remove", "--force", tree)
	patch, err := gitIn(tree, "diff", fixed, fixed+"~1", "--", "*.java", ":!*src/test*", ":!*/test/*")
	if err != nil || patch == "" {
		res.Problems = "no main code in the fix"
		return res
	}
	pfile := filepath.Join(work, "bug.patch")
	_ = os.WriteFile(pfile, []byte(patch+"\n"), 0o644)
	if msg, err := gitIn(tree, "apply", "--whitespace=nowarn", pfile); err != nil {
		res.Problems = "apply: " + msg
		return res
	}
	_, _ = gitIn(tree, "add", "-A")
	if msg, err := gitIn(tree, "commit", "-q", "-m", "Reintroduce the bug"); err != nil {
		res.Problems = "commit: " + msg
		return res
	}
	repo, err := git.Open(tree)
	if err != nil {
		res.Problems = err.Error()
		return res
	}
	sha := repo.Head()
	changes, _ := repo.Changes(sha)
	res.Targets = map[string][]int{}
	for _, ch := range changes {
		res.Targets[ch.Path] = ch.Added
	}
	for i, callers := range []bool{false, true} {
		st, err := store.Open(filepath.Join(work, fmt.Sprint("db", i)), "r")
		if err != nil {
			res.Problems = err.Error()
			return res
		}
		r := &review.Reviewer{Repo: repo, Store: st, Model: client, MaxFiles: 8, Callers: callers}
		start := time.Now()
		v := variant{}
		if err := r.Review(context.Background(), sha, review.Options{}); err != nil {
			v.Error = err.Error()
		}
		if rv, ok := st.GetReview(sha); ok && rv.Note != "" && v.Error == "" {
			v.Error = rv.Note
		}
		v.Took = time.Since(start).Seconds()
		for _, f := range st.Findings(sha) {
			fd := finding{Path: f.Path, Title: f.Title, Source: f.Source, Line: f.Line}
			for _, t := range res.Targets[f.Path] {
				if abs(f.Line-t) <= locate {
					fd.Located = true
				}
			}
			if fd.Located {
				v.Located++
			}
			v.Findings = append(v.Findings, fd)
		}
		st.Close()
		if callers {
			res.With = v
		} else {
			res.Without = v
		}
	}
	return res
}

func abs(n int) int {
	if n < 0 {
		return -n
	}
	return n
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, "review:", err)
	os.Exit(1)
}
