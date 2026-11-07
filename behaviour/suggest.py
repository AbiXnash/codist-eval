"""Approach B: the model reads the commit and suggests inputs as plain JSON values, never code.

For each bug, the model gets the commit's diff and the signatures of the changed methods (from javap)
and returns, per method, lists of argument values. The harness checks every value against the
parameter types and drops what does not fit. Writes <bug>/inputs.json and <bug>/suggest.log.
Usage: python3 suggest.py [bug-id ...]
"""
import json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("MODEL", "qwen2.5-coder:14b")
URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

SYSTEM = """You help test a change to Java code. You get a commit's diff and the signatures of the methods it changed.
Suggest argument values that are likely to make the old and the new code behave differently: inputs that reach
the changed lines. Use only plain JSON values: strings, numbers, booleans, null, and arrays of strings.
For a date use "yyyy-mm-dd". For an enum use the constant's name. For a char use a one-letter string.
For byte[], InputStream or Reader give the content as a string. Give each method at most 8 argument lists,
each with exactly one value per parameter, in order. Reply with JSON only."""

SCHEMA = {"type": "object", "properties": {"methods": {"type": "array", "items": {"type": "object", "properties": {
    "method": {"type": "string"},
    "calls": {"type": "array", "items": {"type": "array", "items": {}}}},
    "required": ["method", "calls"]}}}, "required": ["methods"]}


def bugs():
    for line in open(os.path.join(HERE, os.environ.get("LIST", "bugs.txt"))):
        if line.strip():
            yield line.split()


def signatures(bug, targets):
    """javap's view of each target method in the new version: name -> list of signature lines."""
    out = {}
    cp = os.path.join(HERE, bug, "new", "classes")
    for t in targets:
        cls, name = t.split("#")
        if name.startswith("<") or name == "main":
            continue
        try:
            text = subprocess.run(["javap", "-p", "-cp", cp, cls], capture_output=True, text=True, timeout=60).stdout
        except Exception:
            continue
        simple = cls.split(".")[-1].split("$")[-1]
        want = re.compile(r"[\s.]" + re.escape(name if name != simple else cls) + r"\(")
        for l in text.splitlines():
            if want.search(" " + l.strip()):
                out.setdefault(t, []).append(l.strip().rstrip(";"))
    return out


def ask(system, user):
    body = json.dumps({"model": MODEL, "stream": False, "format": SCHEMA, "keep_alive": "30m",
                       "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1500},
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(URL + "/api/chat", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1200) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def main():
    only = set(sys.argv[1:])
    for bug, repo, sha in bugs():
        if only and bug not in only:
            continue
        targets = [l.strip() for l in open(os.path.join(HERE, bug, "methods.txt")) if l.strip()]
        sigs = signatures(bug, targets)
        if not sigs:
            print(bug, "no methods to ask about")
            continue
        git = os.path.expanduser("~/.cache/codist-bench/repos/" + repo)
        diff = subprocess.run(["git", "-C", git, "diff", "-U8", sha + "~1", sha, "--", "*.java", ":!*src/test*"],
                              capture_output=True, text=True).stdout[:9000]
        msg = subprocess.run(["git", "-C", git, "log", "-1", "--format=%s", sha], capture_output=True, text=True).stdout.strip()
        lines = ["## Commit", msg, "", "## Diff", "```diff", diff, "```", "", "## Methods to call (Java signatures)"]
        for t, ss in sigs.items():
            for s in ss:
                lines.append(f"- {t}: {s}")
        lines.append('\nReply as {"methods":[{"method":"pkg.Class#name","calls":[[arg, ...], ...]}]}')
        start = time.time()
        try:
            reply = ask(SYSTEM, "\n".join(lines))
        except Exception as e:
            print(bug, "model failed:", e)
            continue
        took = time.time() - start
        inputs = {}
        for m in reply.get("methods", []):
            key = m.get("method", "")
            if key not in sigs:  # the model may shorten the name
                key = next((t for t in sigs if t.endswith("#" + key.split("#")[-1].split(".")[-1])), key)
            inputs.setdefault(key, []).extend(c for c in m.get("calls", []) if isinstance(c, list))
        json.dump(inputs, open(os.path.join(HERE, bug, "inputs.json"), "w"), indent=1, ensure_ascii=False)
        with open(os.path.join(HERE, bug, "suggest.log"), "w") as f:
            f.write("\n".join(lines) + "\n\n## Reply\n" + json.dumps(reply, indent=1, ensure_ascii=False))
        print(f"{bug}: {sum(len(v) for v in inputs.values())} argument lists for {len(inputs)} methods in {took:.0f}s")


if __name__ == "__main__":
    main()
