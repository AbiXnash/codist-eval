#!/bin/bash
# run.sh [A|B] [list]: runs the harness on every bug, each in its own empty folder. A: edge cases; B: the model's values.
cd "$(dirname "$0")"
mode=${1:-A}
mkdir -p reports
list=${2:-bugs.txt}
while read id repo sha; do
  [ -z "$id" ] && continue
  w=$(mktemp -d)
  ( cd $w && java -Xmx1g -cp "$OLDPWD/harness" Harness "$OLDPWD/$id" $mode ) > reports/$id.$mode.txt 2>&1
  rm -rf $w
  echo "$id: $(head -1 reports/$id.$mode.txt)"
done < $list
