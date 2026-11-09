# codist-eval

Measurements for [Codist](https://github.com/AbiXnash/codist): what its review and its ideas actually catch, on real
bugs from open-source Java projects.

## behaviour: does running the code catch bugs?

The question: if Codist runs the methods a commit changed, on the code before and after, with the same inputs, how
often does a real bug show a difference, and how often does a harmless change show one?

- `changed/` lists the methods a commit changed and the project methods that call them, using
  [codist-java](https://github.com/AbiXnash/codist-java).
- `harness/Harness.java`, written once and never by the model, calls them on both versions in separate class
  loaders and compares what a caller can see: return value, exception, and arguments after the call.
- Inputs are **A**, standard edge cases per type, or **B**, plain values the local model suggests after reading the
  commit.

Results so far, in [behaviour/RESULTS.md](behaviour/RESULTS.md): on 10 benchmark bugs, A shows the real difference in
4 and A with B in 5; on 22 refactoring commits that should not change behaviour, neither shows a false alarm.

### Run it

Needs Java 21, Maven, Go, git and Python 3; B also needs a model server such as Ollama. The benchmark repositories
are cloned to `~/.cache/codist-bench/repos` (as the Codist benchmark does).

```bash
cd behaviour
./setup.sh bugs.txt          # check out and compile each commit and its parent, list changed methods
./run.sh A bugs.txt          # edge cases
LIST=bugs.txt python3 suggest.py && ./run.sh B bugs.txt   # the model's values
```

`select_refactors.py` picks the refactoring commits; `refactors-labels.txt` is how each was labelled by hand before
any result.

## testbed: test projects with planted bugs

Each script builds a small project commit by commit, with bugs planted in some commits and clean commits (a feature,
a fix, a refactor) in between. Every commit compiles. The answer key is written here, outside the project, so
Codist never sees it.

| Script | Project | Planted bugs | Clean commits |
|---|---|---|---|
| `make_records_lab.py` | [records-lab](https://github.com/AbiXnash/records-lab): a Spring Boot gateway serving an employee directory as JSON, XML, CSV and GraphQL over JDBC | 19 | 5 |
| `make_shop_lab.py` | [shop-lab](https://github.com/AbiXnash/shop-lab): two Spring Boot services (orders, payments) with Feign, Redis, Spring Batch and JDBC | 24 | 6 |
| `make_maze_lab.py` | [maze-lab](https://github.com/AbiXnash/maze-lab): Glowmaze, an original maze-chase game in Java 21 Swing, written to a design spec | 19 | 3 |

Bugs come in kinds: known Java mistakes, logic slips, ones that break the project's written rules, and ones only
careful reading finds. `score_shop_lab.py` scores a running Codist against any answer key: a bug is found when an
alarm (not a note) lands within 6 lines of it, and a clean commit fails if it gets any alarm.

```bash
python3 testbed/make_maze_lab.py ~/dev/maze-lab          # build the project
codist ~/dev/maze-lab                                    # let Codist review every commit
python3 testbed/score_shop_lab.py http://localhost:8080 testbed/maze-lab-truth.json
```

Latest results, `qwen2.5-coder:14b` on a 16 GB laptop:

| Run | Found | Clean commits with an alarm |
|---|---|---|
| [records-lab-run2.txt](testbed/records-lab-run2.txt) | 18 of 19 | 0 of 5 |
| [shop-lab-run3.txt](testbed/shop-lab-run3.txt) | 20 of 24 | 0 of 6 |
| [maze-lab-run2.txt](testbed/maze-lab-run2.txt) | 15 of 19 | 2 of 3, both low |

On the game, the misses are mostly changed numbers its spec states (an interval of 20 s set to 10 s, 60 updates per
second set to 30). `triage/` holds the experiment behind the feedback triage model.

## Licence

Source available under the [PolyForm Noncommercial License 1.0.0](LICENSE): free for any noncommercial purpose, such
as personal study, research, hobby projects and testing, and for use by charities, schools, public research and
public health bodies and government institutions. **Using it for a business, or in anything sold, needs a commercial
licence** from the author: open an issue at [github.com/AbiXnash/codist](https://github.com/AbiXnash/codist/issues)
to ask. Third-party code included in Codist keeps its own licence.

Required Notice: Copyright 2026 Abinash (https://github.com/AbiXnash)
