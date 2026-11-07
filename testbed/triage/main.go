// Command triage measures Codist's false-alarm filter on shop-lab: it learns from one run's labelled model findings,
// as if a team had marked them useful or wrong, and reports what it would do to another run's findings.
//
//	go run . run1.json run2.json
package main

import (
	"encoding/json"
	"fmt"
	"os"

	review "github.com/AbiXnash/codist-review"
	"github.com/AbiXnash/codist-review/store"
)

type row struct {
	Kind, Severity, Source, Title, Detail, Doubt string
	Useful                                       bool
}

func load(path string) []row {
	raw, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	var rs []row
	if err := json.Unmarshal(raw, &rs); err != nil {
		panic(err)
	}
	return rs
}

func finding(r row) store.Finding {
	return store.Finding{Source: r.Source, Severity: r.Severity, Title: r.Title, Detail: r.Detail, Doubt: r.Doubt}
}

func main() {
	train, test := load(os.Args[1]), load(os.Args[2])
	var ex []review.TriageExample
	for _, r := range train {
		ex = append(ex, review.TriageExample{Finding: finding(r), Useful: r.Useful})
	}
	t := review.TrainTriage(ex)
	if t == nil {
		fmt.Println("too few judged findings to train")
		return
	}
	shown := func(sev string) bool { return sev == "critical" || sev == "high" || sev == "medium" }
	var before, after [2]int // [wrong, useful] shown as problems (medium or above)
	for _, r := range test {
		p := t.Useful(finding(r))
		demoted := p < 0.3
		i := map[bool]int{false: 0, true: 1}[r.Useful]
		if shown(r.Severity) {
			before[i]++
			if !demoted {
				after[i]++
			}
		}
		mark := " "
		if demoted {
			mark = "↓"
		}
		fmt.Printf("%s p=%.2f useful=%-5v %-8s %s\n", mark, p, r.Useful, r.Severity, r.Title)
	}
	fmt.Printf("\nshown as problems (medium or above)  before: %d wrong, %d useful   after: %d wrong, %d useful\n",
		before[0], before[1], after[0], after[1])
}
