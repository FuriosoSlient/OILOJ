"""Local judge: compiles GNU C++20 and runs submissions with resource limits."""
import os, sys, subprocess, tempfile, time, signal, shutil, json, threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Cross-platform helpers (Windows / Linux / macOS)
# ---------------------------------------------------------------------------
IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""          # suffix for compiled binaries

try:
    import resource                     # POSIX only; used to report peak memory
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False


def _popen_kwargs():
    """Kwargs that put the child into its own process group so we can kill
    the whole tree on TLE. setsid is POSIX-only; Windows uses creationflags."""
    if IS_WIN:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}   # POSIX: equivalent to setsid()


def kill_tree(proc):
    """Kill a process and its children, portably."""
    if proc is None:
        return
    try:
        if IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def exe_path(path) -> str:
    """Return the executable path with the platform suffix applied."""
    p = str(path)
    if IS_WIN and not p.lower().endswith(".exe"):
        p += ".exe"
    return p


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_text(path, data):
    Path(path).write_text(data or "", encoding="utf-8", newline="\n")

DATA_DIR = Path(__file__).parent / "data" / "problems"
BIN_DIR = Path(__file__).parent / "data" / "bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)
LIB_DIR = Path(__file__).parent / "data" / "lib"     # holds testlib.h

STATUS_MAP = {
    "AC": "Accepted",
    "WA": "Wrong Answer",
    "TLE": "Time Limit Exceeded",
    "MLE": "Memory Limit Exceeded",
    "RE": "Runtime Error",
    "CE": "Compilation Error",
    "SE": "System Error",
}

def compile_cpp(source_path: str, out_path: str, extra_flags=None, extra_sources=None) -> tuple[bool, str]:
    out_path = exe_path(out_path)
    flags = ["g++", "-std=c++20", "-O2", "-w", "-o", out_path, source_path]
    if extra_sources:
        flags += [str(s) for s in extra_sources if s]
    # Always expose testlib.h so special judges / interactors can include it.
    if LIB_DIR.exists():
        flags += [f"-I{LIB_DIR}"]
    if extra_flags:
        flags += extra_flags
    try:
        p = subprocess.run(flags, capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            return False, p.stderr[-2000:]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Compilation timed out"
    except Exception as e:
        return False, str(e)

def _pump(stream, sink, data=None):
    """Feed stdin / drain a pipe in a helper thread."""
    try:
        if data is not None:
            try:
                stream.write(data)
            except (BrokenPipeError, OSError):
                pass
            finally:
                try: stream.close()
                except Exception: pass
        else:
            sink.append(stream.read())
    except Exception:
        if data is None:
            sink.append(b"")


def safe_io_name(name):
    n = os.path.basename((name or "").strip())
    if not n or n in (".", "..") or "/" in n or "\\" in n:
        return ""
    return n


def _stage_input(work, stdin_data, stdin_path, file_in):
    """Place input in the sandbox without keeping a second Python copy.

    Returns (stdin_handle_or_None, payload_bytes_or_None, named_in_path).
    Prefer opening the original testdata file (or a copy/hardlink) so the judge
    process does not hold the whole case in RAM while the child also reads it —
    that double-counting is what produced false MLEs.
    """
    fin = safe_io_name(file_in)
    named = (work / fin) if (work and fin) else None
    src = Path(stdin_path) if stdin_path else None
    if src and src.is_file():
        if named:
            try:
                if named.exists() or named.is_symlink():
                    named.unlink()
            except Exception:
                pass
            try:
                os.link(src, named)
            except Exception:
                try:
                    shutil.copyfile(src, named)
                except Exception:
                    write_text(named, read_text(src))
            return open(named, "rb"), None, named
        return open(src, "rb"), None, None
    text = stdin_data if isinstance(stdin_data, str) else (
        (stdin_data or b"").decode("utf-8", errors="replace"))
    if named:
        write_text(named, text)
        return open(named, "rb"), None, named
    payload = text.encode("utf-8") if text else b""
    return None, payload, None


def _read_vmhwm_kb(pid):
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])
    except Exception:
        return 0
    return 0


def run_process(bin_path, stdin_data, time_limit_ms, memory_limit_mb,
                cwd=None, file_in=None, file_out=None, stdin_path=None):
    """Run a binary; returns (rc, stdout, stderr, status, elapsed_ms, max_rss_kb).

    I/O is pumped by helper threads and the child is reaped with os.wait4(), which
    reports THIS process's peak RSS. (resource.getrusage(RUSAGE_CHILDREN) is a
    sticky high-water mark across all children and would misreport memory.)
    """
    tl = max(0.05, time_limit_ms / 1000.0)
    work = Path(cwd) if cwd else None
    fout = safe_io_name(file_out)
    stdin_f = None
    stdin_f, payload, _named = _stage_input(work, stdin_data, stdin_path, file_in)
    if work and fout:
        try:
            (work / fout).unlink()
        except Exception:
            pass

    popen_kw = dict(
        args=[bin_path],
        stdin=stdin_f if stdin_f is not None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(work) if work else None,
        **_popen_kwargs(),
    )

    try:
        proc = subprocess.Popen(**popen_kw)
    except Exception as e:
        try:
            if stdin_f:
                stdin_f.close()
        except Exception:
            pass
        return -1, "", str(e), "RE", 0, 0
    redirected_in = stdin_f is not None
    try:
        if stdin_f:
            stdin_f.close()
    except Exception:
        pass
    stdin_f = None

    out_buf, err_buf = [], []
    threads = []
    if not redirected_in:
        threads.append(threading.Thread(target=_pump, args=(proc.stdin, None, payload or b""), daemon=True))
    threads.append(threading.Thread(target=_pump, args=(proc.stdout, out_buf), daemon=True))
    threads.append(threading.Thread(target=_pump, args=(proc.stderr, err_buf), daemon=True))
    t0 = time.time()
    for t in threads:
        t.start()

    rc, max_rss_kb, timed_out, term_sig = None, 0, False, 0
    if _HAS_RESOURCE and not IS_WIN:
        while True:
            hwm = _read_vmhwm_kb(proc.pid)
            if hwm > max_rss_kb:
                max_rss_kb = hwm
            try:
                pid, sts, ru = os.wait4(proc.pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pid, sts, ru = proc.pid, 0, None
            if pid:
                if ru is not None:
                    max_rss_kb = max(max_rss_kb, int(ru.ru_maxrss))
                if os.WIFSIGNALED(sts):
                    term_sig = os.WTERMSIG(sts)
                    rc = -term_sig
                else:
                    rc = os.WEXITSTATUS(sts)
                proc.returncode = rc
                break
            if time.time() - t0 > tl:
                timed_out = True
                kill_tree(proc)
                try:
                    _p, sts, ru = os.wait4(proc.pid, 0)
                    if ru is not None:
                        max_rss_kb = max(max_rss_kb, int(ru.ru_maxrss))
                    if os.WIFSIGNALED(sts):
                        term_sig = os.WTERMSIG(sts)
                    proc.returncode = -9
                except (ChildProcessError, OSError):
                    proc.returncode = -9
                break
            time.sleep(0.002)
    else:
        try:
            rc = proc.wait(timeout=tl)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
            try:
                rc = proc.wait(timeout=2)
            except Exception:
                rc = -9

    elapsed = (time.time() - t0) * 1000
    for t in threads:
        t.join(timeout=2)

    stdout = (out_buf[0] if out_buf else b"").decode(errors="replace")
    stderr = (err_buf[0] if err_buf else b"").decode(errors="replace")
    if work and fout:
        fp = work / fout
        if fp.exists():
            stdout = read_text(fp)

    if sys.platform == "darwin":
        max_rss_kb //= 1024

    try:
        ml_kb = int(memory_limit_mb or 0) * 1024
    except (TypeError, ValueError):
        ml_kb = 0

    if timed_out:
        if ml_kb and max_rss_kb > ml_kb:
            return -1, stdout, stderr, "MLE", elapsed, max_rss_kb
        return -1, stdout, stderr, "TLE", tl * 1000, max_rss_kb

    over_mem = bool(ml_kb and max_rss_kb > ml_kb)
    if over_mem:
        return (rc if rc is not None else -1), stdout, stderr, "MLE", elapsed, max_rss_kb

    status = "AC"
    if rc is None or rc != 0:
        status = "RE"

    return (rc if rc is not None else -1), stdout, stderr, status, elapsed, max_rss_kb


def token_compare(a: str, b: str) -> bool:
    return a.split() == b.split()


def is_functional(problem) -> bool:
    return (problem.get("checker_type") or "") == "functional"


def compile_functional(user_src, out_bin, pdir, work) -> tuple[bool, str]:
    """Link contestant code with grader.cpp (grader provides main)."""
    pdir = Path(pdir)
    work = Path(work)
    header = pdir / "interaction.h"
    grader = pdir / "grader.cpp"
    if header.exists():
        try:
            shutil.copy(header, work / "interaction.h")
        except Exception:
            pass
    extras, flags = [], [f"-I{work}", f"-I{pdir}"]
    if grader.exists() and (grader.read_text(encoding="utf-8", errors="replace") or "").strip():
        gdst = work / "grader.cpp"
        try:
            shutil.copy(grader, gdst)
        except Exception:
            write_text(gdst, read_text(grader))
        extras.append(str(gdst))
    else:
        return False, "函数式交互缺少 grader.cpp（main 必须写在 grader 里，由 grader 读入数据）"
    return compile_cpp(str(user_src), str(out_bin), extra_flags=flags, extra_sources=extras)


def functional_verdict(status, rc, out, expected):
    if status in ("TLE", "MLE", "SE"):
        return status
    if status == "RE":
        if rc in (1, 2):
            return "WA"
        if rc in (0, 7):
            status = "AC"
        else:
            return "RE"
    if status == "AC":
        if expected is not None:
            return "AC" if token_compare(out, expected) else "WA"
        return "AC"
    return status


def judge_submission(problem, code, hack_input=None, progress=None):
    """
    Evaluate a submission.
    problem is a dict with: id, slug, time_limit, memory_limit, subtasks, validator, interactive.
    If hack_input is provided, runs ONLY that input (used by Hack judging).
    `progress(case_results, partial_score)` is invoked after every testcase so the
    caller can stream live results to the browser.
    Returns dict: status, score, subtask_scores, case_results, message
    """
    slug = problem["slug"]
    pdir = DATA_DIR / slug
    pdir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="judge_"))
    try:
        src = work / "sol.cpp"
        binp = work / ("sol" + EXE)
        write_text(src, code)
        functional = is_functional(problem)
        if functional:
            ok, err = compile_functional(src, binp, pdir, work)
        else:
            ok, err = compile_cpp(str(src), str(binp))
        if not ok:
            return {"status": "CE", "score": 0, "subtask_scores": [],
                    "case_results": [], "message": err}

        subtasks = problem.get("subtasks") or []
        tl = problem.get("time_limit", 1000)
        ml = problem.get("memory_limit", 256)
        validator_src = problem.get("validator")
        interactive = 0 if functional else problem.get("interactive", 0)
        fio_in = safe_io_name(problem.get("file_io_in") or "")
        fio_out = safe_io_name(problem.get("file_io_out") or "")

        # Compile custom validator/interactor if present.
        # For interactive problems, `validator` points to an already-compiled interactor binary.
        checker_bin = None
        interactor_bin = None
        if interactive:
            candidates = []
            if validator_src:
                candidates += [Path(validator_src), pdir / validator_src]
            candidates += [pdir / "interactor", pdir / ("interactor" + EXE)]
            for c in candidates:
                c = Path(exe_path(c))
                if c.exists():
                    interactor_bin = str(c)
                    break
            if not interactor_bin:
                # last resort: compile spj.cpp as the interactor
                isrc = pdir / "spj.cpp"
                idst = pdir / ("interactor" + EXE)
                if isrc.exists():
                    okc, errc = compile_cpp(str(isrc), str(idst))
                    if okc:
                        interactor_bin = str(idst)
                    else:
                        return {"status": "SE", "score": 0, "subtask_scores": [],
                                "case_results": [], "message": f"interactor 编译失败: {errc}"}
                else:
                    return {"status": "SE", "score": 0, "subtask_scores": [],
                            "case_results": [], "message": "interactor binary missing"}
        else:
            # Special judge: a testlib-based C++ checker stored per problem.
            # It is compiled ahead of time by the admin UI; if the binary is
            # missing but we have the source, build it on demand.
            spj_bin = spj_binary_for(problem)
            spj_src = (DATA_DIR / problem["slug"] / "spj.cpp") if problem.get("slug") else None
            if problem.get("checker_type") == "spj" and spj_src and spj_src.exists():
                if not (spj_bin and spj_bin.exists()):
                    okc, errc = compile_spj(spj_src, spj_bin)
                    if not okc:
                        return {"status": "SE", "score": 0, "subtask_scores": [],
                                "case_results": [], "message": f"SPJ 编译失败: {errc}"}
                checker_bin = spj_bin
            elif validator_src and os.path.exists(validator_src):
                checker_bin = work / ("checker" + EXE)
                ok2, err2 = compile_cpp(validator_src, str(checker_bin))
                if not ok2:
                    return {"status": "SE", "score": 0, "subtask_scores": [],
                            "case_results": [], "message": f"checker compile error: {err2}"}

        # --- HACK mode: single input ---
        if hack_input is not None:
            inp = hack_input
            if interactive and interactor_bin:
                # interactor receives input data as arg/file and communicates
                ok, msg = run_interactive(str(binp), interactor_bin, inp, tl, pdir)
                return {"status": "AC" if ok else "WA", "score": 100 if ok else 0,
                        "subtask_scores": [100 if ok else 0],
                        "case_results": [{"status": "AC" if ok else "WA", "message": msg}],
                        "message": msg}
            rc, out, err, status, elapsed, _ = run_process(
                str(binp), inp, tl, ml, cwd=str(work), file_in=fio_in or None, file_out=fio_out or None)
            if status != "AC":
                return {"status": status, "score": 0, "subtask_scores": [0],
                        "case_results": [{"status": status, "time": elapsed}], "message": ""}
            # compare against expected output.
            # Prefer an explicitly provided hack_ref.out; otherwise compute expected output
            # by running the problem's reference solution (pdir/ref).
            expected = None
            ref_file = pdir / "hack_ref.out"
            if ref_file.exists():
                expected = read_text(ref_file)
            else:
                ref_bin = Path(exe_path(pdir / "ref"))
                ref_src = pdir / "ref.cpp"
                # The exec bit can be lost (archive/restore, Windows checkouts...).
                # Repair it, and rebuild from source if the binary is missing.
                if ref_bin.exists() and not os.access(ref_bin, os.X_OK):
                    try:
                        ref_bin.chmod(0o755)
                    except Exception:
                        pass
                if not ref_bin.exists() and ref_src.exists():
                    compile_cpp(str(ref_src), str(ref_bin))
                if ref_bin.exists():
                    rrc, rout, rerr, rstatus, _, _ = run_process(
                        str(ref_bin), inp, max(tl, 10000), ml,
                        cwd=str(work), file_in=fio_in or None, file_out=fio_out or None)
                    if rstatus == "AC":
                        expected = rout
                    else:
                        # Reference failed on this input -> the input is likely invalid.
                        return {"status": "SE", "score": 0, "subtask_scores": [0],
                                "case_results": [{"status": "SE"}],
                                "message": f"标程在该输入上失败({rstatus})，可能是非法输入数据"}
            if checker_bin:
                okc, msgc = run_checker(str(checker_bin), inp, out, expected, pdir)
                status = "AC" if okc else "WA"
            elif expected is None:
                # Never silently accept: without a reference we cannot judge a hack.
                return {"status": "SE", "score": 0, "subtask_scores": [0],
                        "case_results": [{"status": "SE"}],
                        "message": "无法判定：该题缺少标程(ref)，无法计算 Hack 输入的正确输出"}
            else:
                status = "AC" if token_compare(out, expected) else "WA"
            return {"status": status, "score": 100 if status=="AC" else 0,
                    "subtask_scores": [100 if status=="AC" else 0],
                    "case_results": [{"status": status, "time": elapsed}], "message": ""}

        # --- NORMAL mode: evaluate all subtasks ---
        subtask_scores = []
        case_results = []
        total = 0
        overall = "AC"
        use_sub = int(problem.get("use_subtasks") if problem.get("use_subtasks") is not None else 1)
        for si, st in enumerate(subtasks):
            st_score = st.get("score", 0)
            tcs = st.get("testcases", [])
            per_case = (not use_sub) or bool(st.get("per_case"))
            got = 0
            all_ok = True
            for tc in tcs:
                infile = pdir / tc["input"]
                outname = tc.get("output") or ""
                outfile = (pdir / outname) if outname else None
                if not infile.exists():
                    case_results.append({"subtask": si, "case": tc.get("input"), "status": "SE",
                                         "message": f"missing {tc['input']}"})
                    all_ok = False
                    continue
                expected = read_text(outfile) if outfile and outfile.exists() else None
                if interactive and interactor_bin:
                    inp = read_text(infile)
                    ok, msg = run_interactive(str(binp), interactor_bin, inp, tl, pdir)
                    status = "AC" if ok else "WA"
                    elapsed = 0
                else:
                    rc, out, err, status, elapsed, _ = run_process(
                        str(binp), None, tl, ml, cwd=str(work),
                        file_in=fio_in or None, file_out=fio_out or None,
                        stdin_path=str(infile))
                    if functional:
                        status = functional_verdict(status, rc, out, expected)
                    elif status == "AC":
                        if checker_bin:
                            inp = read_text(infile)
                            okc, msgc = run_checker(str(checker_bin), inp, out, expected, pdir)
                            status = "AC" if okc else "WA"
                        elif expected is not None:
                            status = "AC" if token_compare(out, expected) else "WA"
                        else:
                            status = "SE"
                tc_max = int(tc.get("score") or 0)
                earned = 0
                if status == "AC":
                    if per_case:
                        earned = tc_max
                        got += earned
                else:
                    all_ok = False
                    if overall == "AC":
                        overall = "WA" if status == "WA" else status
                case_results.append({
                    "subtask": si, "case": tc.get("input"), "status": status,
                    "time": int(elapsed), "score": earned,
                    "max_score": tc_max if per_case else int(st_score or 0),
                })
                if progress:
                    try:
                        progress(case_results, total + got)
                    except Exception:
                        pass
            if not per_case:
                if all_ok and tcs:
                    got = st_score
            subtask_scores.append(got)
            total += got
        full = problem.get("score_total") or 0
        # 0-score Hack 点失败时原题仍可能满分，不能因此标成 AC。
        all_cases_ok = bool(case_results) and all(c.get("status") == "AC" for c in case_results)
        if all_cases_ok and total >= full:
            overall = "AC"
        elif total > 0:
            if overall not in ("TLE", "MLE", "RE", "SE"):
                overall = "WA"  # partial credit / 满分未过 Hack
        else:
            if overall == "AC":
                overall = "WA"
        if not subtasks:
            # fall back: all test cases in a flat tests directory
            total = 0
        return {"status": overall, "score": total, "subtask_scores": subtask_scores,
                "case_results": case_results, "message": ""}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def compile_spj(source_path, out_path):
    """Compile a testlib-based special judge. Returns (ok, log)."""
    return compile_cpp(str(source_path), str(out_path))


def spj_binary_for(problem):
    """Path of the compiled SPJ for a problem, or None when it has no SPJ."""
    slug = problem.get("slug")
    if not slug:
        return None
    return Path(exe_path(DATA_DIR / slug / "spj"))


# testlib exit codes: 0=OK 1=WA 2=PE 3=FAIL 7=points
TESTLIB_CODES = {0: "AC", 1: "WA", 2: "WA", 3: "SE", 7: "AC"}


def run_checker(checker_bin, input_data, output_data, expected, pdir):
    """Run a standard testlib-style or simple checker: args <input> <output> <answer>.
    Our checker convention: reads stdin lines: INPUT, then '---ENDINPUT---', OUTPUT, '---ENDOUTPUT---', ANSWER.
    Simpler: checker is invoked with three file paths."""
    work = Path(tempfile.mkdtemp(prefix="chk_"))
    try:
        ifi = work / "in.txt"; ofi = work / "out.txt"; afi = work / "ans.txt"
        write_text(ifi, input_data)
        write_text(ofi, output_data)
        write_text(afi, expected or "")
        p = subprocess.run([exe_path(checker_bin), str(ifi), str(ofi), str(afi)],
                           capture_output=True, text=True, timeout=10, cwd=str(pdir),
                           encoding="utf-8", errors="replace")
        # testlib writes its verdict to stderr and signals via the exit code.
        msg = ((p.stderr or "") + (p.stdout or "")).strip()[:500]
        if p.returncode in (0, 7):
            return True, msg
        return False, msg
    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run_interactive(sol_bin, interactor_bin, input_data, tl, pdir):
    """interactor is invoked as: interactor <input_file> <output_log> and communicates with solution via pipes.
    We use a simpler protocol: interactor reads input from argv[1], then reads solution's stdout and writes to solution's stdin.
    We wire sol.stdin -> interactor.stdout; interactor.stdin -> sol.stdout."""
    work = Path(tempfile.mkdtemp(prefix="iact_"))
    iproc = sproc = None
    try:
        ifi = work / "input.txt"
        ofi = work / "output.txt"
        write_text(ifi, input_data)
        # interactor <input> <output_log> ; then interactor communicates over its stdin/stdout with sol
        iproc = subprocess.Popen(
            [exe_path(interactor_bin), str(ifi), str(ofi)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(pdir), **_popen_kwargs(),
        )
        sproc = subprocess.Popen(
            [exe_path(sol_bin)],
            stdin=iproc.stdout, stdout=iproc.stdin, stderr=subprocess.PIPE,
            cwd=str(pdir), **_popen_kwargs(),
        )
        # close parent's copies
        iproc.stdout.close()
        iproc.stdin.close()
        t0 = time.time()
        while True:
            if iproc.poll() is not None or sproc.poll() is not None:
                break
            if time.time() - t0 > tl:
                for p in (iproc, sproc):
                    kill_tree(p)
                return False, "Interaction time limit exceeded"
            time.sleep(0.02)
        try:
            sproc.wait(timeout=2)
        except Exception:
            kill_tree(sproc)
        rc_i = iproc.returncode
        # interactor outputs verdict on stderr last line "OK" or "WRONG_ANSWER ..."
        err = iproc.stderr.read().decode(errors="replace") if iproc.stderr else ""
        if rc_i == 0:
            return True, err.strip()[-300:]
        return False, err.strip()[-300:] or "Interaction failed"
    except Exception as e:
        return False, str(e)
    finally:
        for p in [iproc, sproc]:
            try:
                p.kill()
            except: pass
        shutil.rmtree(work, ignore_errors=True)


# ===========================================================================
# Hack evaluation
# ===========================================================================
# A hack is only meaningful if the input itself is legitimate, so we run it in
# three stages and report every stage back to the UI:
#
#   1. 标程 (std)      -> must produce a correct answer, otherwise the input is
#                         rejected as invalid (INVALID, nobody is penalised).
#   2. 攻击者程序       -> the attacker must also solve their own input; if their
#                         code fails, the hack is rejected (INVALID).
#   3. 被 Hack 的程序   -> executed REPEATEDLY (default 5 runs). A single failing
#                         run is enough for the hack to succeed, which catches
#                         non-deterministic code (uninitialised memory, hash
#                         randomisation, races, unstable sorts...).

HACK_VICTIM_RUNS = 5


def _prepare_reference(pdir, tl, ml, problem=None):
    """Ensure pdir/ref exists and is executable. Returns the path or None."""
    ref_bin = Path(exe_path(pdir / "ref"))
    ref_src = pdir / "ref.cpp"
    if problem and is_functional(problem) and ref_src.exists():
        work = Path(tempfile.mkdtemp(prefix="ref_"))
        try:
            ok, _ = compile_functional(ref_src, ref_bin, pdir, work)
            if ok and ref_bin.exists():
                try:
                    ref_bin.chmod(0o755)
                except Exception:
                    pass
                return ref_bin
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if ref_bin.exists() and not os.access(ref_bin, os.X_OK):
        try:
            ref_bin.chmod(0o755)
        except Exception:
            pass
    if not ref_bin.exists() and ref_src.exists():
        compile_cpp(str(ref_src), str(ref_bin))
    return ref_bin if ref_bin.exists() else None


def _build_checker(problem, pdir, work):
    """Resolve the checker binary for a problem (SPJ or legacy validator)."""
    if problem.get("checker_type") == "spj":
        spj_src = pdir / "spj.cpp"
        spj_bin = spj_binary_for(problem)
        if spj_bin and spj_bin.exists() and not os.access(spj_bin, os.X_OK):
            try:
                spj_bin.chmod(0o755)
            except Exception:
                pass
        if spj_src.exists() and not (spj_bin and spj_bin.exists()):
            ok, log = compile_spj(spj_src, spj_bin)
            if not ok:
                return None, f"SPJ 编译失败: {log[:300]}"
        if spj_bin and spj_bin.exists():
            return str(spj_bin), ""
    validator_src = problem.get("validator")
    if validator_src and os.path.exists(validator_src):
        out = work / ("checker" + EXE)
        ok, log = compile_cpp(validator_src, str(out))
        if not ok:
            return None, f"checker 编译失败: {log[:300]}"
        return str(out), ""
    return None, ""


def _run_one(binp, inp, tl, ml, label, cwd=None, file_in=None, file_out=None,
             functional=False):
    """Execute a program once and package the outcome for the UI."""
    rc, out, err, status, elapsed, rss = run_process(
        str(binp), inp, tl, ml, cwd=cwd, file_in=file_in, file_out=file_out)
    if functional:
        status = functional_verdict(status, rc, out, None)
    return {
        "label": label,
        "status": status,
        "time_ms": int(elapsed),
        "memory_kb": int(rss),
        "output": out[:4000],
        "stderr": (err or "")[:1000],
        "truncated": len(out) > 4000,
    }


def run_subtask_validator(source: str, hack_input: str, pdir: Path):
    """Compile and run a testlib-style validator against hack input.

    Exit 0 / _ok => legal for this subtask. Anything else => illegal.
    """
    if not (source or "").strip():
        return True, ""
    work = Path(tempfile.mkdtemp(prefix="val_"))
    try:
        src = work / "val.cpp"
        out = work / ("val" + EXE)
        write_text(src, source)
        ok, log = compile_cpp(str(src), str(out))
        if not ok:
            return False, f"子任务校验器编译失败: {log[:300]}"
        ifi = work / "in.txt"
        write_text(ifi, hack_input)
        p = subprocess.run([str(out), str(ifi)], input=hack_input,
                           capture_output=True, text=True, timeout=10,
                           encoding="utf-8", errors="replace", cwd=str(pdir))
        msg = ((p.stderr or "") + (p.stdout or "")).strip()[:400]
        if p.returncode in (0, 7):
            return True, msg
        return False, msg or f"校验器拒绝该数据 (exit {p.returncode})"
    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def evaluate_hack(problem, victim_code, hack_input, attacker_code=None,
                  runs=HACK_VICTIM_RUNS, subtask_indices=None):
    """Full hack pipeline. Returns a dict describing every stage.

    verdict: SUCCESS | FAILURE | INVALID | SE
    """
    slug = problem["slug"]
    pdir = DATA_DIR / slug
    tl = problem.get("time_limit", 1000)
    ml = problem.get("memory_limit", 256)
    work = Path(tempfile.mkdtemp(prefix="hack_"))
    detail = {"stages": [], "runs": [], "checker": "", "runs_requested": runs}

    try:
        # ---- stage 1: standard solution -------------------------------------
        hv = (problem.get("hack_validator") or "").strip()
        if not hv:
            for st in (problem.get("subtasks") or []):
                if (st.get("validator") or "").strip():
                    hv = st["validator"]
                    break
        if hv:
            okv, msgv = run_subtask_validator(hv, hack_input, pdir)
            if not okv:
                return {"verdict": "INVALID",
                        "message": f"数据校验器拒绝该输入：{msgv}",
                        "detail": detail}

        ref_bin = _prepare_reference(pdir, tl, ml, problem)
        if not ref_bin:
            return {"verdict": "INVALID",
                    "message": "该题缺少标程(ref.cpp)，无法验证 Hack 数据",
                    "detail": detail}
        # The reference gets a generous time budget and no memory cap: it only has
        # to establish the correct answer, and it may legitimately use more memory
        # than a contestant's solution is allowed.
        fio_in = safe_io_name(problem.get("file_io_in") or "")
        fio_out = safe_io_name(problem.get("file_io_out") or "")
        fun = is_functional(problem)
        std = _run_one(ref_bin, hack_input, max(tl * 5, 10000), 0, "标准程序 (std)",
                       cwd=str(work), file_in=fio_in or None, file_out=fio_out or None,
                       functional=fun)
        detail["stages"].append(std)
        if std["status"] != "AC":
            return {"verdict": "INVALID",
                    "message": f"标程在该输入上失败({std['status']})，判定为非法输入数据",
                    "detail": detail}
        expected = std["output"]

        checker_bin, cerr = _build_checker(problem, pdir, work)
        if cerr:
            return {"verdict": "SE", "message": cerr, "detail": detail}
        detail["checker"] = ("函数式交互" if fun else
                             ("SPJ (testlib)" if checker_bin else "逐 token 比对"))

        def verify(out_text):
            """Judge one contestant output against the std answer."""
            if checker_bin:
                ok, msg = run_checker(checker_bin, hack_input, out_text, expected, pdir)
                return ok, (msg or ("通过" if ok else "未通过"))
            ok = token_compare(out_text, expected)
            return ok, ("输出一致" if ok else "输出与标程不一致")

        # ---- stage 2: attacker's own solution --------------------------------
        if attacker_code:
            abin = work / ("atk" + EXE)
            ok, clog = compile_cpp_source(attacker_code, abin, work, "atk.cpp", problem, pdir)
            if not ok:
                return {"verdict": "INVALID",
                        "message": f"攻击方代码编译失败，无法验证数据合法性: {clog[:300]}",
                        "detail": detail}
            atk = _run_one(abin, hack_input, tl, ml, "攻击方程序",
                           cwd=str(work), file_in=fio_in or None, file_out=fio_out or None,
                           functional=fun)
            if atk["status"] == "AC":
                okc, msg = verify(atk["output"])
                atk["checker"] = msg
                if not okc:
                    atk["status"] = "WA"
            else:
                atk["checker"] = "未产生有效输出"
            detail["stages"].append(atk)
            if atk["status"] != "AC":
                return {"verdict": "INVALID",
                        "message": f"攻击方自己的程序未能通过该数据({atk['status']})，Hack 无效",
                        "detail": detail}

        # ---- stage 3: victim, executed `runs` times --------------------------
        vbin = work / ("victim" + EXE)
        ok, clog = compile_cpp_source(victim_code, vbin, work, "victim.cpp", problem, pdir)
        if not ok:
            detail["stages"].append({"label": "被 Hack 程序", "status": "CE",
                                     "time_ms": 0, "memory_kb": 0,
                                     "output": "", "stderr": clog[:1000],
                                     "checker": "编译失败"})
            return {"verdict": "SUCCESS", "message": "被 Hack 的代码无法编译", "detail": detail}

        failed_run = None
        for i in range(max(1, runs)):
            r = _run_one(vbin, hack_input, tl, ml, f"被 Hack 程序 第 {i+1}/{runs} 次",
                         cwd=str(work), file_in=fio_in or None, file_out=fio_out or None)
            if r["status"] == "AC":
                okc, msg = verify(r["output"])
                r["checker"] = msg
                if not okc:
                    r["status"] = "WA"
            else:
                r["checker"] = "未产生有效输出"
            detail["runs"].append(r)
            if r["status"] != "AC" and failed_run is None:
                failed_run = r
                break          # one failure is enough

        detail["runs_executed"] = len(detail["runs"])
        if failed_run:
            return {"verdict": "SUCCESS",
                    "message": f"第 {len(detail['runs'])} 次运行失败（{failed_run['status']}）：{failed_run.get('checker','')}",
                    "detail": detail}
        return {"verdict": "FAILURE",
                "message": f"连续 {len(detail['runs'])} 次运行均通过，Hack 失败",
                "detail": detail}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def compile_cpp_source(code, out_bin, work, filename="tmp.cpp", problem=None, pdir=None):
    """Compile in-memory C++ source to `out_bin`."""
    src = work / filename
    write_text(src, code)
    if problem and is_functional(problem) and pdir:
        return compile_functional(src, out_bin, pdir, work)
    return compile_cpp(str(src), str(out_bin))
