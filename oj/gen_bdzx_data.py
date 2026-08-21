#!/usr/bin/env python3
"""Generate strong ICPC testdata for the 8 Baidu Star problems (bdzx_1..8)."""
from __future__ import annotations
import os, random, subprocess, tempfile, shutil, textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "data" / "problems"
SRC = Path("/tmp/ojzip/oj/data/problems")
MOD = 998244353
rng = random.Random(20260821)

FIXES = {
    "usingnamespacestd;": "using namespace std;",
    "elsecout": "else cout",
    "return0;": "return 0;",
}

def load_std(i: int) -> str:
    p = SRC / f"bdzx_{i}" / "ref.cpp"
    s = p.read_text(encoding="utf-8", errors="replace")
    for a, b in FIXES.items():
        s = s.replace(a, b)
    return s

def compile_std(i: int, extra=None) -> Path:
    src = Path(tempfile.mkdtemp(prefix=f"std{i}_")) / "ref.cpp"
    src.write_text(load_std(i), encoding="utf-8")
    out = src.with_suffix("")
    cmd = ["g++", "-O2", "-std=c++20", "-o", str(out), str(src)]
    if extra:
        cmd[1:1] = extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"compile bdzx_{i} failed:\n{r.stderr[-1500:]}")
    return out

def run_std(binp: Path, inp: str, timeout=60) -> str:
    r = subprocess.run([str(binp)], input=inp, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"std RE {r.returncode} {r.stderr[-400:]}")
    return r.stdout

def write_case(slug: str, idx: int, inp: str, out: str):
    d = ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"0_{idx}.in").write_text(inp, encoding="utf-8", newline="\n")
    (d / f"0_{idx}.out").write_text(out if out.endswith("\n") else out + "\n", encoding="utf-8", newline="\n")
    print(f"  {slug} 0_{idx}  in={len(inp):,}B  out={len(out):,}B")

def rand_tree(n: int):
    edges = []
    for v in range(2, n + 1):
        u = rng.randint(1, v - 1)
        edges.append((u, v))
    rng.shuffle(edges)
    return edges

def path_tree(n):
    return [(i, i + 1) for i in range(1, n)]

def star_tree(n, c=1):
    return [(c, i) if i != c else (1, 2) for i in range(1, n + 1) if i != c][: n - 1]

def dump_tree_case(n, edges):
    lines = [str(n)]
    for u, v in edges:
        if rng.random() < 0.5:
            u, v = v, u
        lines.append(f"{u} {v}")
    return "\n".join(lines)

def gen1(binp):
    slug = "bdzx_1"
    cases = []
    # sample
    cases.append("3\n3\n1 2\n2 3\n7\n1 4\n5 3\n2 4\n1 6\n4 3\n3 7\n10\n1 5\n5 2\n2 10\n5 8\n1 4\n5 6\n4 3\n2 7\n9 5\n")
    # many tiny
    t, parts, sn = [], [], 0
    for _ in range(20000):
        n = 2
        parts.append(dump_tree_case(n, [(1, 2)]))
        sn += n
        if sn >= 200000:
            break
    cases.append(str(len(parts)) + "\n" + "\n".join(parts) + "\n")
    # max path / star (n <= 1e5)
    n = 100000
    cases.append("1\n" + dump_tree_case(n, path_tree(n)) + "\n")
    cases.append("1\n" + dump_tree_case(n, [(1, i) for i in range(2, n + 1)]) + "\n")
    # mixed random to sum n = 2e5
    parts, sn = [], 0
    while sn < 200000:
        rest = 200000 - sn
        if rest < 2:
            break
        n = rng.randint(2, min(5000, rest))
        kind = rng.choice(["rand", "path", "star", "bin"])
        if kind == "path":
            e = path_tree(n)
        elif kind == "star":
            e = [(rng.randint(1, 3) if n > 3 else 1, i) for i in range(2, n + 1)]
            e = [(1 if a == i else a, i) for a, i in e]
        elif kind == "bin":
            e = [(max(1, i // 2), i) for i in range(2, n + 1)]
        else:
            e = rand_tree(n)
        parts.append(dump_tree_case(n, e))
        sn += n
    cases.append(str(len(parts)) + "\n" + "\n".join(parts) + "\n")
    for i, inp in enumerate(cases):
        write_case(slug, i, inp, run_std(binp, inp, 20))

def simulate_pvz(n, m, k, a, buy):
    c = [0] * (m + 1)
    for hp in a:
        dead = False
        for x in range(1, m + 1):
            hp -= 1
            c[x] += 1
            if buy[x] and c[x] % k == 0:
                hp = 0
            if hp <= 0:
                dead = True
                break
        if not dead:
            return False
    return True

def pvz_min(n, m, k, a):
    best = None
    for mask in range(1 << m):
        buy = [False] * (m + 1)
        cost = 0
        for i in range(m):
            if mask >> i & 1:
                buy[i + 1] = True
                cost += 1
        if best is not None and cost >= best:
            continue
        if simulate_pvz(n, m, k, a, buy):
            best = cost if best is None else min(best, cost)
    return best

def gen2():
    slug = "bdzx_2"
    samples = [
        ("5 4 2\n1 3 5 2 5\n", "1\n"),
        ("6 6 3\n1 2 7 5 7 7\n", "2\n"),
        ("15 8 3\n1 4 7 1 5 4 9 9 8 2 4 4 3 5 3\n", "3\n"),
        ("1 2 2\n3\n", "Zombies are on your lawn\n"),
        ("20 10 3\n10 6 6 2 11 11 8 6 3 11 10 4 11 5 3 5 2 9 10 5\n", "3\n"),
    ]
    extra = []
    extra.append((f"100 100 3\n" + " ".join(["1"] * 100) + "\n", "0\n"))
    extra.append((f"100 100 2\n" + " ".join(["100"] * 100) + "\n", "0\n"))
    extra.append(("1 1 2\n2\n", "Zombies are on your lawn\n"))
    extra.append(("1 1 3\n1\n", "0\n"))
    # brute-forceable strong-ish
    for m, n, k in [(8, 12, 2), (10, 15, 3), (12, 12, 2)]:
        a = [rng.randint(1, m + 1) for _ in range(n)]
        ans = pvz_min(n, m, k, a)
        out = "Zombies are on your lawn\n" if ans is None else f"{ans}\n"
        extra.append((f"{n} {m} {k}\n" + " ".join(map(str, a)) + "\n", out))
    # all survive-need: hp = m+1, m small
    n, m, k = 10, 8, 3
    a = [m + 1] * n
    ans = pvz_min(n, m, k, a)
    extra.append((f"{n} {m} {k}\n" + " ".join(map(str, a)) + "\n",
                  "Zombies are on your lawn\n" if ans is None else f"{ans}\n"))
    for i, (inp, out) in enumerate(samples + extra):
        write_case(slug, i, inp, out)

def gen3(binp):
    slug = "bdzx_3"
    cases = []
    cases.append("5\n0 1 3 5 6\n")
    cases.append("8\n0 0 1 1 5 10 15 18\n")
    cases.append("1\n0\n")
    cases.append("1\n1000000\n")
    n = 200000
    cases.append(f"{n}\n" + " ".join(["0"] * n) + "\n")
    a = list(range(n))  # 0..n-1
    rng.shuffle(a)
    cases.append(f"{n}\n" + " ".join(map(str, a)) + "\n")
    a = [rng.randint(0, 10**6) for _ in range(n)]
    cases.append(f"{n}\n" + " ".join(map(str, a)) + "\n")
    a = [0] * (n // 2) + [1] * (n // 4) + [rng.choice([2, 3, 4, 6, 8, 9, 12, 16, 24, 36]) for _ in range(n - n // 2 - n // 4)]
    rng.shuffle(a)
    cases.append(f"{n}\n" + " ".join(map(str, a)) + "\n")
    a = [rng.randrange(0, 64) for _ in range(n)]
    cases.append(f"{n}\n" + " ".join(map(str, a)) + "\n")
    for i, inp in enumerate(cases):
        write_case(slug, i, inp, run_std(binp, inp, 15))

def gen4(binp):
    slug = "bdzx_4"
    cases = []
    cases.append("3\n3 4\n1 5\n7 7\n")
    pairs = []
    pairs.append((1, 1))
    pairs.append((2, 2))
    pairs.append((10**9, 10**9))
    pairs.append((1, 10**9))
    pairs.append((10**9 - 1, 10**9))
    pairs.append((2, 3))
    pairs.append((3, 5))
    pairs.append((100, 200))
    pairs.append((10**8, 10**8 + 3))
    while len(pairs) < 100000:
        if rng.random() < 0.1:
            x = rng.randint(1, 10**9)
            pairs.append((x, x))
        else:
            l = rng.randint(1, 10**9 - 1)
            r = rng.randint(l, min(10**9, l + rng.choice([1, 2, 3, 10, 100, 10**6, 10**9])))
            pairs.append((l, r))
    cases.append(str(len(pairs)) + "\n" + "\n".join(f"{l} {r}" for l, r in pairs) + "\n")
    for i, inp in enumerate(cases):
        write_case(slug, i, inp, run_std(binp, inp, 15))

def mersenne_ok(c):
    return c > 0 and ((c + 1) & c) == 0  # c = 2^k - 1

def gen5(binp):
    slug = "bdzx_5"
    cases = []
    cases.append("3\n3\n1 2 1\n5\n1 1 1 2 3\n7\n2 2 2 2 2 2 2\n")
    def one(n, arr):
        return f"{n}\n" + " ".join(map(str, arr))
    parts = []
    # Yes: single run of 2^k-1
    for k in range(0, 12):
        c = (1 << k) - 1
        if c == 0:
            continue
        parts.append(one(c, [1] * c))
    # Yes: concatenated distinct blocks with mersenne lengths
    arr = [1] * 7 + [2] * 1 + [3] * 15 + [4] * 3
    parts.append(one(len(arr), arr))
    # No: split same value
    parts.append(one(5, [1, 2, 1, 2, 1]))
    parts.append(one(4, [1, 1, 2, 2]))  # counts 2 not mersenne
    # maxish many tests
    sn = sum(int(p.split()[0]) for p in parts)
    while sn < 400000:
        n = rng.randint(1, 200)
        if rng.random() < 0.4:
            # yes-like one value
            k = rng.choice([1, 3, 7, 15, 31, 63])
            n = k
            arr = [rng.randint(1, n)] * n
        else:
            arr = [rng.randint(1, n) for _ in range(n)]
        parts.append(one(n, arr))
        sn += n
    # one huge Yes all equal 2^20-1 too big; use 2^18-1? 262143
    n = (1 << 18) - 1  # 262143
    parts.append(one(n, [1] * n))
    sn += n
    # huge No
    n = 500000
    arr = [1] * (n // 2) + [2] * (n - n // 2)
    parts.append(one(n, arr))
    sn += n
    # fill remaining with random up to 2e6
    while sn < 2000000:
        n = min(10000, 2000000 - sn)
        if n <= 0:
            break
        arr = [rng.randint(1, n) for _ in range(n)]
        parts.append(one(n, arr))
        sn += n
    cases.append(str(len(parts)) + "\n" + "\n".join(parts) + "\n")
    # another file: t large n=1
    t = 100000
    cases.append(str(t) + "\n" + "\n".join("1\n1" for _ in range(t)) + "\n")
    for i, inp in enumerate(cases):
        write_case(slug, i, inp, run_std(binp, inp, 30))

def gen6(binp):
    slug = "bdzx_6"
    cases = []
    cases.append("2\n11 11\n15 15\n1\n3\n")
    # several disjoint singleton intervals
    n = 50
    xs = sorted(rng.sample(range(1, 2**20), n))
    body = [str(n)] + [f"{x} {x}" for x in xs]
    q = 200
    qs = [rng.choice(xs) if rng.random() < 0.5 else rng.randint(1, 2**20 - 1) for _ in range(q)]
    body.append(str(q))
    body += [str(x) for x in qs]
    cases.append("\n".join(body) + "\n")
    # ranges of length 2^k
    segs = []
    cur = 1
    for k in range(0, 12):
        L = 1 << k
        segs.append((cur, cur + L - 1))
        cur += L + rng.randint(1, 5)
    n = len(segs)
    q = 500
    body = [str(n)] + [f"{l} {r}" for l, r in segs]
    body.append(str(q))
    for _ in range(q):
        body.append(str(rng.randint(1, cur)))
    cases.append("\n".join(body) + "\n")
    # denser but not 1e4 if memory dies — try n=200 q=2000
    n = 200
    segs = []
    cur = 1
    for i in range(n):
        L = rng.choice([1, 1, 2, 4, 8, 16, 32, 64])
        segs.append((cur, cur + L - 1))
        cur += L + rng.randint(1, 10)
    q = 2000
    body = [str(n)] + [f"{l} {r}" for l, r in segs] + [str(q)]
    for _ in range(q):
        body.append(str(rng.randint(1, min(2**30 - 1, cur + 1000))))
    cases.append("\n".join(body) + "\n")
    for i, inp in enumerate(cases):
        try:
            out = run_std(binp, inp, 25)
        except Exception as e:
            print("  bdzx_6 skip", i, e)
            continue
        write_case(slug, i, inp, out)

def gen7(binp):
    slug = "bdzx_7"
    cases = []
    cases.append("5\n2 3\n1 5\n3 3\n2 6 1\n4 5\n5 5 5 5\n5 1000000000\n1000000000 1000000000 1000000000 1000000000 1000000000\n10 100\n97 135 103 130 147 89 93 215 175 261\n")
    # t max, n=1
    t = 200000
    lines = [str(t)]
    for _ in range(t):
        s = rng.randint(0, 10**9)
        p = rng.randint(0, 10**9)
        lines.append(f"1 {s}")
        lines.append(str(p))
    cases.append("\n".join(lines) + "\n")
    # one n = 2e5
    n = 200000
    s = 0
    p = [rng.randint(0, 10**9) for _ in range(n)]
    cases.append(f"1\n{n} {s}\n" + " ".join(map(str, p)) + "\n")
    n = 200000
    s = 10**9
    p = [10**9] * n
    cases.append(f"1\n{n} {s}\n" + " ".join(map(str, p)) + "\n")
    # decreasing / increasing
    n = 50000
    cases.append(f"1\n{n} 10\n" + " ".join(str(i) for i in range(n)) + "\n")
    cases.append(f"1\n{n} 10\n" + " ".join(str(n - i) for i in range(n)) + "\n")
    for i, inp in enumerate(cases):
        write_case(slug, i, inp, run_std(binp, inp, 20))

def gen8(binp):
    """Force-online: encode with lst. We keep lst=0 for all ops except we put
    type-3 queries at the very end (single query => still lst=0 for encoding),
    plus a small fully-encoded test built from the sample pattern.
    """
    slug = "bdzx_8"
    cases = []
    cases.append("2 7\n1 1 2 9\n1 2 9 1\n1 1 2 1\n2 2 3\n3 1 2 1\n1 8 14 9\n3 8 15 11\n")

    def inserts_then_rev_then_one_query(k, n_ins, n_rev):
        ops = []
        n = 0
        for i in range(n_ins):
            pos = rng.randint(1, n + 1)
            a = rng.randint(1, 10**9 - 1)
            b = rng.randint(1, 10**9 - 1)
            ops.append(f"1 {pos} {a} {b}")
            n += 1
        for _ in range(n_rev):
            l = rng.randint(1, n)
            r = rng.randint(l, n)
            ops.append(f"2 {l} {r}")
        l = rng.randint(1, n)
        r = rng.randint(l, n)
        c = rng.randint(0, k - 1)
        ops.append(f"3 {l} {r} {c}")
        return f"{k} {len(ops)}\n" + "\n".join(ops) + "\n"

    cases.append(inserts_then_rev_then_one_query(2, 5000, 2000))
    cases.append(inserts_then_rev_then_one_query(7, 8000, 3000))
    cases.append(inserts_then_rev_then_one_query(14, 3000, 2000))
    cases.append(inserts_then_rev_then_one_query(30, 2000, 1000))
    # max inserts, few reverses, one query (lst=0 throughout encoding)
    k, q = 2, 200000
    n_rev = 29999
    n_ins = q - n_rev - 1
    ops, n = [], 0
    for i in range(n_ins):
        pos = rng.randint(1, n + 1)
        ops.append(f"1 {pos} {rng.randint(1,10**9-1)} {rng.randint(1,10**9-1)}")
        n += 1
    for _ in range(n_rev):
        l = rng.randint(1, n); r = rng.randint(l, n)
        ops.append(f"2 {l} {r}")
    l = rng.randint(1, n); r = rng.randint(l, n)
    ops.append(f"3 {l} {r} {rng.randint(0, k-1)}")
    cases.append(f"{k} {len(ops)}\n" + "\n".join(ops) + "\n")
    for i, inp in enumerate(cases):
        print("  try bdzx_8", i, "bytes", len(inp), flush=True)
        write_case(slug, i, inp, run_std(binp, inp, 90))

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    print("generate")
    print("  g++ 1"); gen1(compile_std(1))
    gen2()
    print("  g++ 3"); gen3(compile_std(3))
    print("  g++ 4"); gen4(compile_std(4))
    print("  g++ 5"); gen5(compile_std(5))
    print("  g++ 7"); gen7(compile_std(7))
    print("  g++ 8"); gen8(compile_std(8))
    print("  g++ 6")
    try:
        gen6(compile_std(6))
    except Exception as e:
        print("  bdzx_6 failed", e)
    for i in range(1, 9):
        d = ROOT / f"bdzx_{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ref.cpp").write_text(load_std(i), encoding="utf-8")
    print("done")

if __name__ == "__main__":
    main()
