#!/bin/bash
# setup.sh [list]: for each "id repo sha" line in list (default bugs.txt), checks out the commit (new/) and its
# parent (old/) from the benchmark's cached clones, compiles both, and lists the changed methods. Needs Java 21,
# Maven (for dependencies) and the clones in ~/.cache/codist-bench/repos (made by eval/bench).
cd "$(dirname "$0")"
list=${1:-bugs.txt}
( cd .. && go build -tags 'grammar_subset grammar_subset_java' -o behaviour/changed/changed ./behaviour/changed ) || exit 1
javac -d harness harness/Harness.java || exit 1
while read id repo sha; do
  [ -z "$id" ] && continue
  R=~/.cache/codist-bench/repos/$repo
  rm -rf $id/old $id/new; mkdir -p $id/old $id/new
  git -C $R archive $sha | tar -x -C $id/new
  git -C $R archive $sha~1 | tar -x -C $id/old
  echo "$id: old $(./compile.sh $id old) / new $(./compile.sh $id new)"
  changed/changed $R $sha $id/old $id/new > $id/methods.txt
done < $list
