#!/usr/bin/env python3
"""Generate modest (hack-friendly) testdata for the 10 contest problems."""
import json, os, random, sqlite3, subprocess, shutil
from pathlib import Path
from math import gcd
from functools import reduce

ROOT = Path(__file__).resolve().parent
PDIR = ROOT / "data" / "problems"
DB = ROOT / "data" / "oj.db"
LIB = ROOT / "data" / "lib"
random.seed(20260818)

def wtext(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s if s.endswith("\n") else s + "\n", encoding="utf-8", newline="\n")

def compile_ref(slug, extra=None):
    src = PDIR / slug / "ref.cpp"
    raw = src.read_text(encoding="utf-8")
    if "< bits/stdc++.h >" in raw:
        src.write_text(raw.replace("< bits/stdc++.h >", "<bits/stdc++.h>"), encoding="utf-8")
    out = PDIR / slug / "ref"
    cmd = ["g++", "-std=c++20", "-O2", "-w", "-o", str(out), str(src)]
    if extra:
        cmd[1:1] = extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"compile {slug} failed:\n{r.stderr[-2000:]}")
    return out

def run_ref(binp, inp, timeout=20):
    r = subprocess.run([str(binp)], input=inp, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"ref crashed rc={r.returncode}\n{r.stderr[:400]}")
    out = r.stdout.replace("\r\n", "\n")
    if out and not out.endswith("\n"):
        out += "\n"
    return out

def save_cases(slug, groups):
    """groups: list of (name, score, [input_str, ...])"""
    pdir = PDIR / slug
    # drop old numbered tests
    for f in pdir.glob("*.in"):
        f.unlink()
    for f in pdir.glob("*.out"):
        f.unlink()
    for f in pdir.glob("*.ans"):
        f.unlink()
    binp = compile_ref(slug)
    subtasks = []
    for si, (name, score, cases) in enumerate(groups):
        tcs = []
        for ci, inp in enumerate(cases):
            if not inp.endswith("\n"):
                inp += "\n"
            inf = f"{si}_{ci}.in"
            ouf = f"{si}_{ci}.out"
            wtext(pdir / inf, inp)
            try:
                out = run_ref(binp, inp)
            except Exception as e:
                print(f"  WARN {slug} {inf}: {e}")
                out = ""
            wtext(pdir / ouf, out)
            tcs.append({"input": inf, "output": ouf})
        subtasks.append({"name": name, "score": score, "testcases": tcs})
    return subtasks

# ---------- generators ----------

def gen_uncredited():
    def one(n, p, kmax=8):
        ks = [random.randint(0, kmax) for _ in range(n)]
        return n, p, ks
    def pack(items):
        lines = [str(len(items))]
        for n, p, ks in items:
            lines.append(f"{n} {p}")
            lines.append(" ".join(map(str, ks)))
        return "\n".join(lines)
    # sample-like
    sample = "2\n5 2\n2 3 4 4 3\n3 1\n2 10 1000"
    st1 = [sample, pack([one(1, 2, 3), one(10, 3, 4), one(8, 2, 5)])]
    st2 = [pack([one(20, 2, 6), one(50, 3, 5), one(100, 4, 4)])]
    st3 = [pack([(30, 1, [random.randint(0, 20) for _ in range(30)]),
                 (80, 1, [random.randint(0, 5) for _ in range(80)])])]
    st4 = [pack([one(40, 2, 8), one(60, 5, 6), one(25, 3, 10)])]
    st5 = [pack([one(80, 7, 6), one(100, 10, 5), one(12, 100, 3)])]
    return [
        ("Subtask 1 n<=10", 10, st1),
        ("Subtask 2 n<=100", 20, st2),
        ("Subtask 3 p=1", 5, st3),
        ("Subtask 4 p<=5", 20, st4),
        ("Subtask 5 无特殊约束", 45, st5),
    ]

def gen_unlover():
    def grid(n, only1=False):
        rows = [[0]*n for _ in range(3)]
        for j in range(n):
            used = [1] if only1 else random.sample(range(1, n+1), 3 if n>=3 else n)
            if n < 3:
                used = [1]*3
            random.shuffle(used)
            signs = [random.choice([-1, 1]) for _ in range(3)]
            # avoid all three same sign of same var issues — just fill
            vals = []
            for i in range(3):
                v = used[i % len(used)]
                rows[i][j] = signs[i] * v
        return rows
    def pack(cases):
        lines = [str(len(cases))]
        for rows in cases:
            n = len(rows[0])
            lines.append(str(n))
            for r in rows:
                lines.append(" ".join(map(str, r)))
        return "\n".join(lines)
    sample = """4
4
1 -2 -3 -2
-4 4 -1 -3
1 2 -2 4
2
1 2
-1 -2
2 -2
5
1 2 3 4 5
-2 3 -4 -5 -1
3 -5 1 2 2
6
1 3 -6 2 5 2
1 3 -2 -3 -6 -5
-2 -1 -3 2 3 1"""
    st1 = [sample, pack([grid(2), grid(3), grid(8), grid(10)])]
    st2 = [pack([grid(4, True), grid(6, True), grid(12, True)])]
    st3 = [pack([grid(15), grid(20), grid(25)])]
    return [
        ("Subtask 1 n<=10", 20, st1),
        ("Subtask 2 仅下标1", 5, st2),
        ("Subtask 3 无特殊约束", 75, st3),
    ]

def gen_never_faced():
    def one(n, k, amax=50):
        a = [random.randint(1, amax) for _ in range(n)]
        return f"{n} {k}\n" + " ".join(map(str, a))
    samples = [
        "4 2\n1 2 3 4",
        "5 3\n5 3 4 2 6",
        "6 4\n5 3 50 2 4 5",
        "4 3\n1 2 3 4",
    ]
    return [
        ("Subtask 1 n<=10", 10, samples + [one(8, 3, 20), one(10, 5, 30)]),
        ("Subtask 2 k=2", 5, [one(30, 2, 40), one(80, 2, 100), one(150, 2, 200)]),
        ("Subtask 3 无特殊约束", 85, [one(80, 20, 100), one(200, 7, 300), one(300, 50, 500)]),
    ]

def gen_unchanging():
    def one(n, m):
        lines = [f"{n} {m}"]
        for _ in range(n):
            l = random.randint(1, max(1, m//2))
            r = random.randint(l, m)
            lines.append(f"{l} {r}")
        return "\n".join(lines)
    return [
        ("Subtask 1", 30, ["2 4\n1 3\n1 2", one(3, 8), one(4, 12)]),
        ("Subtask 2", 70, ["5 10\n1 10\n1 10\n1 10\n1 10\n1 10",
                           "5 100\n1 94\n1 96\n1 91\n4 96\n6 97",
                           one(6, 40), one(8, 50)]),
    ]

def gen_evil():
    sample = """7
3 0
3 3
1 1
2 1
3 1
3 2
1 1
2 1
6 2
2 3
4 2
2 3
1 2
2 2
1 1
4 3
2 2
3 2
4 2
3 2
2 3
3 3"""
    def one(n, m):
        bans = set()
        while len(bans) < m:
            bans.add((random.randint(1, n), random.randint(1, n)))
        lines = [f"{n} {m}"]
        for i, x in bans:
            lines.append(f"{i} {x}")
        return "\n".join(lines)
    pack = lambda cs: str(len(cs)) + "\n" + "\n".join(cs)
    return [
        ("Subtask 1 n<=8", 40, [sample, pack([one(4, 2), one(5, 4), one(6, 0)])]),
        ("Subtask 2 n<=15", 60, [pack([one(10, 8), one(12, 15), one(15, 10)])]),
    ]

def gen_heartbreaking():
    # valid small trees + one impossible
    cases = [
        "3 2\n1 2 LEFT\n1 3 RIGHT",
        "1 0",
        "4 2\n1 2 LEFT\n1 4 RIGHT",
        "5 3\n1 2 LEFT\n1 4 RIGHT\n4 5 RIGHT",
        "4 2\n1 2 RIGHT\n2 1 LEFT",  # likely IMPOSSIBLE
        "6 1\n1 3 LEFT",
        "8 3\n1 2 LEFT\n1 6 RIGHT\n6 7 LEFT",
    ]
    return [("Subtask 1", 50, cases)]

def gen_dream():
    def one(vals):
        return f"{len(vals)}\n" + " ".join(map(str, vals))
    return [
        ("Subtask 1", 50, [
            "3\n10 6 15",
            "7\n30 60 21 42 70 15 30",
            one([8, 12, 18]),
            one([7, 14, 21, 35]),
            one([9, 15, 25, 35, 21]),
            one([2, 4, 8, 16]),          # gcd>1 -> -1
            one([1, 6, 10]),
            one([11, 22, 33, 13]),
        ])
    ]

def gen_surrendered():
    # singletons always valid
    def singles(s):
        n = len(s)
        lines = [f"{n} {n}", s]
        for i in range(1, n+1):
            lines.append("1")
            lines.append(str(i))
        return "\n".join(lines)
    sample = """7 3
0011100
3
1 4 6
3
3 4 7
2
2 3"""
    return [
        ("Subtask 1", 50, [
            sample,
            singles("0"),
            singles("1"),
            singles("010"),
            singles("00110"),
            singles("1100110"),
            singles("000111000"),
        ])
    ]

def gen_unsevering():
    def path(n):
        lines = [str(n)]
        for i in range(1, n):
            a = random.randint(1, 20)
            b = random.randint(1, 30)
            lines.append(f"{i} {i+1} {a} {b}")
        return "\n".join(lines)
    def star(n):
        lines = [str(n)]
        for i in range(2, n+1):
            lines.append(f"1 {i} {random.randint(1,10)} {random.randint(1,10)}")
        return "\n".join(lines)
    sample = """2
4
1 2 1 10
2 3 100 10
3 4 1 10
5
1 2 1 1
1 3 1 1
1 4 1 1
1 5 1 1"""
    pack = lambda trees: str(len(trees)) + "\n" + "\n".join(trees)
    return [
        ("Subtask 1", 50, [
            sample,
            pack([path(6), star(7)]),
            pack([path(10), star(8), path(5)]),
        ])
    ]

def gen_twining():
    # interactive: only .in (n and array). keep a_i small so partition DP is easy / hackable
    cases = [
        "4\n10 4 6 3",
        "6\n4 5 5 11 3 2",
        "3\n1 1 1",
        "5\n2 2 2 2 2",
        "4\n1 2 3 6",
        "2\n5 5",
        "7\n1 1 1 1 1 1 1",
    ]
    return cases

def update_db(mapping):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for slug, sts in mapping.items():
        blob = json.dumps(sts, ensure_ascii=False)
        con.execute("UPDATE problems SET subtasks=? WHERE slug=?", (blob, slug))
        print(f"  db {slug}: {len(sts)} subtasks, "
              f"{sum(len(s['testcases']) for s in sts)} files")
    # twining: mark interactive so judge uses interactor
    con.execute("UPDATE problems SET interactive=1, checker_type='interactive' WHERE slug='twining_threads'")
    con.commit()
    con.close()

def compile_interactor(slug):
    src = PDIR / slug / "spj.cpp"
    out = PDIR / slug / "interactor"
    cmd = ["g++", "-std=c++20", "-O2", "-w", f"-I{LIB}", "-o", str(out), str(src)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("interactor compile failed", r.stderr[-1500:])
    else:
        print("  interactor built", out)

def main():
    mapping = {}
    jobs = [
        ("uncredited", gen_uncredited),
        ("unlover", gen_unlover),
        ("never_faced", gen_never_faced),
        ("unchanging", gen_unchanging),
        ("evil_defining", gen_evil),
        ("heartbreaking", gen_heartbreaking),
        ("dream_ending", gen_dream),
        ("surrendered_witnessing", gen_surrendered),
        ("unsevering", gen_unsevering),
    ]
    for slug, fn in jobs:
        print("==", slug)
        mapping[slug] = save_cases(slug, fn())

    print("== twining_threads (interactive inputs only)")
    slug = "twining_threads"
    pdir = PDIR / slug
    for f in list(pdir.glob("*.in")) + list(pdir.glob("*.out")):
        f.unlink()
    tcs = []
    for i, inp in enumerate(gen_twining()):
        name = f"0_{i}.in"
        wtext(pdir / name, inp)
        tcs.append({"input": name, "output": ""})
    mapping[slug] = [{"name": "Subtask 1", "score": 50, "testcases": tcs}]
    compile_interactor(slug)

    # compile heartbreaking spj
    src = PDIR / "heartbreaking" / "spj.cpp"
    out = PDIR / "heartbreaking" / "spj"
    r = subprocess.run(["g++", "-std=c++20", "-O2", "-w", f"-I{LIB}", "-o", str(out), str(src)],
                       capture_output=True, text=True)
    print("heartbreaking spj", "ok" if r.returncode==0 else r.stderr[-800:])

    update_db(mapping)
    print("done")

if __name__ == "__main__":
    main()
