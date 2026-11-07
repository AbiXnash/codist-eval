# Behaviour-difference experiment, 2026-11-06

Question: if Codist runs the methods a commit changed, on the code before and after, with the same inputs, how many
real bugs show a difference? Same 10 benchmark bugs as the earlier re-scoring sample; each "commit" is the bug's
fix, so the code before is buggy and the code after is fixed.

## How

1. `changed` (Go, on Codist's own Java parser and call graph) lists the methods the fix changed, plus the project
   methods that call them.
2. Both versions are compiled from source with their Maven dependencies (`compile.sh`). All 10 compile.
3. `harness/Harness.java`, written once and never by the model, loads each version in its own class loader and calls
   every listed method with the same inputs. It compares the return value, the exception type, the arguments after
   the call (text written to an `Appendable`, for one) and the object's fields that exist in both versions. The buggy
   version also runs against itself, and inputs whose result changes between runs are not counted.
   - **A**: standard edge cases per type, one parameter at a time, plus seeded mixes (up to 300 calls per method).
     Objects are built from the class's constants, constructors, factory methods or concrete subclasses.
   - **B**: the local model (`qwen2.5-coder:14b`) reads the commit and suggests plain JSON values; the harness checks
     each value against the parameter's type and fills parameters it left out with A's values.

## Results

| bug | A (edge cases) | B (model's values) | what differs |
|---|---|---|---|
| Csv-4 | yes | yes | buggy `getHeaderMap()` throws NullPointerException |
| Csv-15 | yes | yes | buggy version quotes non-ASCII text such as `ÿé中` |
| solarpositioning | yes | yes | ΔT estimates differ for 2010 to 2100 and later years |
| ensembler | yes | yes | button text differs |
| epubcheck | no | yes | `--help` and `--version`: buggy `processArguments` returns false, fixed true |
| crawler-commons | no | no | the model's robots.txt had no `User-agent` line, so both ignore it |
| Cli-4 | no | no | needs `Options` holding a required option: a built-up object |
| JxPath-16 | no | no | needs DOM nodes |
| jsoup | no | no | needs a parsed document |
| ByteSkript | no | no | compiles scripts; results change between runs, so nothing can be compared |
| **total** | **4 of 10** | **5 of 10** | |

False alarms: none in the final run. One appeared earlier (epubcheck: the fix added a field, so the object always
looked different) and is fixed by comparing only fields both versions have. Differences between runs were caught by
the control run (215 inputs in ByteSkript) and left out.

Cost: A runs in seconds to a few minutes per bug. B adds one model call per commit, 12 to 77 seconds here.

## What it means

The agreed bar was about 3 of 10 with few false alarms. A alone gives 4 and A with B gives 5, with no false alarms, so
"show the behaviour difference and ask if it was meant" passes as a direction.

## False alarms on refactors (2026-11-07)

Every commit above was a fix, so a difference was always expected. To count false alarms, the same harness ran on
commits meant not to change behaviour. `select_refactors.py` picked them by a rule fixed before any result: the
subject says refactor, rename, clean up, simplify, extract, tidy, reformat or polish, and not fix, bug, add and so
on; only main Java files changed, at most 3 files and 60 lines; the newest 3 per repository. That gave 27 commits,
26 of which compile (`refactors.txt`). Each diff was read and labelled before any result (`refactors-labels.txt`):
22 should not change behaviour, and 4 change it on purpose although the message says refactor.

| | A (edge cases) | B (model's values) |
|---|---|---|
| 22 commits that should not change behaviour: shown as different | **0** | **0** |
| reported as notes, not differences | 3 | 1 |
| 4 commits that change behaviour on purpose: caught | 2 | 1 |

The first run of A had 2 false alarms, both fixed by a rule checked against the bug results first (none of the 5
caught bugs needed it): results now compare what a caller can see (return value, exception, arguments after the
call); a difference only in private fields is a note, and so is a NullPointerException that happens only because
the harness passed null. The jsoup commit that clears a field it no longer needs is the first kind; a ByteSkript
method that now throws on a null class nobody passes is the second.

Caught: crawler-commons 5f1f1e5c (A: `a/../b` is no longer collapsed in resolved URLs) and epubcheck 9d5af07d (A and
B: an invalid media type now becomes empty). Missed: ByteSkript f83861b9, which only changes what is registered at
start-up, and epubcheck 1c0b93bd, whose changed error text the inputs never reached.

Caveat: "no difference" also happens when the inputs never reach the changed lines, which the harness cannot see
without coverage. Several refactor commits ran few calls (ensembler d159d528: 2).

With the bugs: A shows the real difference in 4 of 10 bugs and none of 22 refactors; A with B, 5 of 10 and none.

Not yet measured:
- The 5 planted Orbit Commerce bugs, which are Spring code with repositories and Feign clients (the agreed Mockito fakes).
- The misses are all built-up objects. Letting the model describe one as data (for example "Options with a required
  option a" as a list of setter calls the harness performs) would target Cli-4, JxPath and jsoup without the model
  writing code.

## Files

Everything is in `eval/behaviour/`. `setup.sh [list]` checks out and compiles each commit and its parent and lists the
changed methods (`changed/`, on Codist's Java parser); `suggest.py` asks the model for inputs (`LIST=file` for
another list); `run.sh A|B [list]` runs `harness/Harness.java`. Per bug: `methods.txt`, `inputs.json`, `suggest.log`;
reports in `reports/<bug>.<A|B>.txt`.
