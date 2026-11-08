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

## Licence

Source available under the [PolyForm Noncommercial License 1.0.0](LICENSE): free for any noncommercial purpose, such
as personal study, research, hobby projects and testing, and for use by charities, schools, public research and
public health bodies and government institutions. **Using it for a business, or in anything sold, needs a commercial
licence** from the author: open an issue at [github.com/AbiXnash/codist](https://github.com/AbiXnash/codist/issues)
to ask. Third-party code included in Codist keeps its own licence.

Required Notice: Copyright 2026 Abinash (https://github.com/AbiXnash)
