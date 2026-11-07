#!/bin/bash
# compile.sh <bug-dir> <old|new>: compiles src/main/java into classes/, with the project's
# dependencies from the local Maven cache (offline). Writes cp.txt and a status line.
d=$1/$2
cd "$d" || exit 1
rm -rf classes; mkdir classes
cp=""
if [ -f pom.xml ]; then
  mvn -q -B dependency:build-classpath -Dmdep.outputFile=cp.txt >mvn.log 2>&1 && cp=$(cat cp.txt)
fi
src=src/main/java; [ -d $src ] || src=src/java
find $src -name '*.java' > files.txt
for rel in 8 11 17 21; do
  if javac --release $rel -nowarn -encoding UTF-8 -proc:none -cp "$cp" -d classes @files.txt >javac.log 2>&1; then
    # resources too, since some code reads them
    [ -d src/main/resources ] && cp -R src/main/resources/. classes/ 2>/dev/null
    echo "ok release=$rel deps=$(echo "$cp" | tr ':' '\n' | grep -c .)"; exit 0
  fi
done
echo "FAIL $(grep -m1 error javac.log)"
