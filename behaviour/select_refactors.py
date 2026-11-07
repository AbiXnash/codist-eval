"""Lists commits meant not to change behaviour, from the same repositories as bugs.txt, as candidates.

Rule, fixed before looking at any result: the subject says refactor, rename, cleanup, simplify, extract, tidy,
reformat or polish, and not fix, bug, add, allow, handle, support or correct; only main Java files changed (tests may
change too); at most 3 main files and 60 changed lines. Newest first. Prints "id repo sha subject" per candidate.
"""
import os, re, subprocess

WORDS = re.compile(r"\b(refactor\w*|renam\w*|clean ?up\w*|simplif\w*|extract\w*|tidy\w*|reformat\w*|polish\w*)\b", re.I)
NOT = re.compile(r"\b(fix\w*|bug\w*|issue|correct\w*|handle|support|add\w*|allow\w*)\b", re.I)
HERE = os.path.dirname(os.path.abspath(__file__))


def commits(git):
    """Commits whose subject matches, with their changed files. The benchmark's clones download file contents only
    when asked, so subjects are filtered first, file names come from the trees alone, and lines are counted only for
    the few commits left."""
    out = subprocess.run(["git", "-C", git, "log", "--no-merges", "--format=%H\x1f%P\x1f%s"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        sha, parents, subject = line.split("\x1f", 2)
        if not parents or not WORDS.search(subject) or NOT.search(subject):
            continue
        names = subprocess.run(["git", "-C", git, "diff", "--no-renames", "--name-only", sha + "~1", sha],
                               capture_output=True, text=True).stdout.split()
        main_files = [n for n in names if n.endswith(".java") and "/test/" not in n and not n.startswith("test")]
        others = [n for n in names if not n.endswith(".java") and "/test/" not in n and not n.startswith("test")]
        if others or not main_files or len(main_files) > 3:
            continue
        stat = subprocess.run(["git", "-C", git, "diff", "--no-renames", "--numstat", sha + "~1", sha, "--"] + main_files,
                              capture_output=True, text=True).stdout
        files = [l.split("\t", 2) for l in stat.strip().splitlines() if l.count("\t") >= 2]
        yield sha, parents, subject, files


def main():
    repos = sorted({l.split()[1] for l in open(os.path.join(HERE, "bugs.txt")) if l.strip()})
    for repo in repos:
        git = os.path.expanduser("~/.cache/codist-bench/repos/" + repo)
        for sha, parents, subject, files in commits(git):
            main_files, lines, other = 0, 0, False
            for a, d, path in files:
                if "/test/" in path or path.startswith("test"):
                    continue
                if not path.endswith(".java"):
                    other = True
                    continue
                main_files += 1
                lines += int(a) + int(d) if a.isdigit() and d.isdigit() else 999
            if other or main_files == 0 or main_files > 3 or lines > 60:
                continue
            name = repo.replace(".git", "").replace("__", "-")
            print(f"{name}-{sha[:8]} {repo} {sha[:10]} {subject[:70]}")


if __name__ == "__main__":
    main()
