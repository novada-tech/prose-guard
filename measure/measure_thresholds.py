#!/usr/bin/env python3
"""Re-measure the share threshold on your own audiences.

    python3 measure/measure_thresholds.py \
        --corpus a.jsonl --audience audience-a \
        --corpus b.jsonl --audience audience-b

Each corpus is lines of {"author": ..., "text": ...} written FOR the audience named beside it. Every
corpus is then scored against every audience, so the diagonal is "scored for the right readers" and
everything off it is "scored for the wrong ones". The threshold worth using is roughly the 90th
percentile of the diagonal: above that, a finding is better explained by the audience being wrong than
by the message being wrong.
"""
import argparse
import json
import os
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "plugins", "prose-guard", "lib"))
import audiences  # noqa: E402
import jargon  # noqa: E402


def load(path, floor=25):
    out = []
    for line in open(path, errors="replace"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        text = str(row.get("text") or "")
        if len(text.split()) >= floor:
            out.append(text)
    return out


def shares(msgs, known):
    rows = []
    for text in msgs:
        bad, considered = jargon.scan(text, lambda t: t.upper() in known)
        if considered:
            rows.append((len(bad), len(considered), len(bad) / len(considered)))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", action="append", required=True)
    ap.add_argument("--audience", action="append", required=True)
    a = ap.parse_args()
    if len(a.corpus) != len(a.audience):
        raise SystemExit("give one --audience per --corpus, in the same order")

    known = {}
    for name in a.audience:
        aud = audiences.ALL.get(name)
        if aud is None:
            raise SystemExit(f"no audience called {name!r}")
        known[name] = aud.known(audiences.BASELINES)

    diagonal, off = [], []
    print(f"{'corpus':28s} {'scored for':22s} {'n':>5s} {'zero':>5s} {'p50':>5s} {'p90':>5s}")
    for path, written_for in zip(a.corpus, a.audience):
        msgs = load(path)
        for name in a.audience:
            rows = shares(msgs, known[name])
            if not rows:
                continue
            sh = sorted(r[2] for r in rows)
            zero = 100 * sum(1 for r in rows if r[0] == 0) / len(rows)
            q = lambda p: sh[int(p * (len(sh) - 1))]  # noqa: E731
            mark = " (right)" if name == written_for else ""
            print(f"{os.path.basename(path)[:27]:28s} {name + mark:22s} {len(rows):5d} "
                  f"{zero:4.0f}% {q(.5):5.2f} {q(.9):5.2f}")
            (diagonal if name == written_for else off).extend(sh)

    if diagonal:
        d = sorted(diagonal)
        print(f"\n90th percentile of the right-audience share: {d[int(.9 * (len(d) - 1))]:.2f}"
              f"   <- the threshold to use")
    if diagonal and off:
        print(f"{'thr':>6s} {'right still blocks':>19s} {'wrong becomes advice':>21s}")
        for thr in (0.2, 0.25, 0.3, 1 / 3, 0.4, 0.5, 0.6):
            keep = 100 * sum(1 for x in diagonal if x <= thr) / len(diagonal)
            stop = 100 * sum(1 for x in off if x > thr) / len(off)
            print(f"{thr:6.2f} {keep:18.1f}% {stop:20.1f}%")


if __name__ == "__main__":
    main()
