"""Scores a running Codist against the shop-lab answer key.

    python3 score_shop_lab.py [http://localhost:8091]

A bug counts as found by a lane when that lane reports a finding in the bug's file within 6 lines of the planted
line. For the refactor control, any finding is a false alarm; for the fix control, the checks should report nothing
new and the earlier issue should be marked resolved.
"""
import json, os, sys, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8091"
HERE = os.path.dirname(os.path.abspath(__file__))
truth = json.load(open(os.path.join(HERE, "shop-lab-truth.json")))


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return json.load(r)


def lane(f):
    src = (f.get("source") or f.get("kind") or "").lower()
    return "checks" if src in ("rule", "rules", "check", "checks", "static") else "model"


rows, totals, rows_findings = [], {}, {}
for t in truth:
    c = get(f"/api/commits/{t['sha']}")
    review = c.get("review") or {}
    findings = [dict(f, path=fl["path"]) for fl in review.get("files", []) for f in fl.get("findings", [])]
    near = [f for f in findings if f["path"] == t["path"] and abs((f.get("line") or 0) - t["line"]) <= 6]
    got = {"checks": any(lane(f) == "checks" for f in near), "model": any(lane(f) == "model" for f in near)}
    b = c.get("behaviour") or {}
    bstat = b.get("status", "")
    got["behaviour"] = (b.get("differ") or 0) > 0
    any_hit = any(got.values())
    if t["kind"].startswith("control"):
        verdict = "false alarm" if findings or got["behaviour"] else "ok"
    else:
        verdict = "found" if any_hit else ("flagged elsewhere" if findings else "missed")
    model_read = bool(review.get("model"))
    rows.append((t, got, bstat, verdict, len(findings), model_read, near))
    rows_findings[t["sha"]] = findings
    k = totals.setdefault(t["kind"], {"n": 0, "found": 0, "checks": 0, "model": 0, "behaviour": 0})
    k["n"] += 1
    k["found"] += verdict == "found"
    for l in ("checks", "model", "behaviour"):
        k[l] += got[l]

for t, got, bstat, verdict, n, read, near in rows:
    lanes = ",".join(l for l in ("checks", "model", "behaviour") if got[l]) or "-"
    others = [f for f in rows_findings[t["sha"]] if f not in near]
    print(f"{t['sha'][:7]} {t['kind']:16} {verdict:17} lanes={lanes:24} findings={n} modelRead={read} "
          f"behaviour={bstat or '-':8} {t['message']}")
    for f in near:
        print(f"        hit   {lane(f)}: {f['path'].split('/')[-1]}:{f.get('line')} {f.get('severity', '')} {f.get('title')}")
    for f in others:
        print(f"        other {lane(f)}: {f['path'].split('/')[-1]}:{f.get('line')} {f.get('severity', '')} {f.get('title')}")
print()
for kind, k in totals.items():
    print(f"{kind:16} {k['found']}/{k['n']} found  (checks {k['checks']}, model {k['model']}, behaviour {k['behaviour']})")
