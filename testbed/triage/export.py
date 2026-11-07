"""Exports the model findings of a shop-lab run with labels from the answer key: useful when the finding is on a
planted bug's line (within 6 lines) in a bug commit, wrong otherwise.

    python3 export.py <codist data dir> > run.json
"""
import glob, json, os, sqlite3, sys
here = os.path.dirname(os.path.abspath(__file__))
truth = {t["sha"]: t for t in json.load(open(os.path.join(here, "..", "shop-lab-truth.json")))}
db = [p for p in glob.glob(os.path.join(sys.argv[1], "shop-lab*.db"))][0]
rows = sqlite3.connect(db).execute(
    "SELECT sha, path, line, severity, source, title, detail, doubt FROM findings WHERE source = 'model'").fetchall()
out = []
for sha, path, line, sev, src, title, detail, doubt in rows:
    t = truth.get(sha)
    if not t:
        continue
    useful = not t["kind"].startswith("control") and path == t["path"] and abs(line - t["line"]) <= 6
    out.append({"sha": sha, "kind": t["kind"], "severity": sev, "source": src, "title": title, "detail": detail,
                "doubt": doubt or "", "useful": useful})
json.dump(out, sys.stdout, indent=1)
