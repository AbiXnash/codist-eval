#!/bin/sh
# Makes qwen3-nothink: qwen3:8b with its "thinking" switched off, so it answers directly. MiroFish calls models
# through the OpenAI client, which cannot turn thinking off per request; a thinking model can spend its whole
# reply on reasoning and return nothing, which breaks MiroFish's JSON parsing. This reuses the same weights.
set -eu
ollama pull qwen3:8b
dir=$(mktemp -d)
ollama show qwen3:8b --template > "$dir/template.txt"
python3 - "$dir" <<'PY'
import sys
d = sys.argv[1]
t = open(d + "/template.txt").read()
a = "{{ if and $.IsThinkSet (not $.Think) -}}"  # the empty think block, normally only when a request asks for it
if t.count(a) != 1:
    sys.exit("qwen3's template has changed; edit this script")
t = t.replace(a, "{{ if true -}}")
open(d + "/Modelfile", "w").write('FROM qwen3:8b\nTEMPLATE """' + t + '"""\n')
PY
ollama create qwen3-nothink -f "$dir/Modelfile"
rm -rf "$dir"
echo "qwen3-nothink is ready"
