"""Persist the crawler database on an independent Git branch."""

import argparse
import gzip
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "catalog.sqlite.gz"
REF = "refs/heads/archive-state"


def git(*args, **kwargs):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, **kwargs)


def result(*args, **kwargs):
    return git(*args, stdout=subprocess.PIPE, text=True, **kwargs).stdout.strip()


def restore(marker):
    remote = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--refs", "origin", REF],
        cwd=ROOT, stdout=subprocess.PIPE, text=True, check=False,
    )
    if remote.returncode == 2:
        marker.write_text("", encoding="ascii")
        print("Using the committed initial archive")
        return
    remote.check_returncode()
    git("fetch", "--no-tags", "origin", REF)
    parent = result("rev-parse", "FETCH_HEAD")
    pending = ARCHIVE.with_suffix(".restore")
    with pending.open("wb") as output:
        git("show", f"{parent}:{ARCHIVE.name}", stdout=output)
    with gzip.open(pending, "rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise ValueError("Remote archive is not a SQLite database")
        while stream.read(1024 * 1024):
            pass
    pending.replace(ARCHIVE)
    marker.write_text(parent, encoding="ascii")
    print(f"Restored {parent}")


def persist(marker):
    parent = marker.read_text(encoding="ascii").strip()
    blob = result("hash-object", "-w", str(ARCHIVE))
    tree = result("mktree", "-z", input=f"100644 blob {blob}\t{ARCHIVE.name}\0")
    if parent and tree == result("rev-parse", f"{parent}^{{tree}}"):
        print("The archive is already current")
        return
    parents = ["-p", parent] if parent else []
    commit = result(
        "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit-tree", tree, *parents, "-m", "Save journal archive state",
    )
    git("push", "origin", f"{commit}:{REF}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("restore", "persist"))
    parser.add_argument("marker", type=Path)
    options = parser.parse_args()
    if options.action == "restore":
        restore(options.marker)
    else:
        persist(options.marker)


if __name__ == "__main__":
    main()


