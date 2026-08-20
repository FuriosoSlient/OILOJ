"""FastAPI application: OJ + OIL contest system, LOJ-style UI."""
import os, sys, json, time, asyncio, threading
from pathlib import Path

# Ensure UTF-8 console output on Windows (GBK default breaks Chinese logs)
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from typing import Optional
from fastapi import FastAPI, Request, Depends, HTTPException, Response, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# Raise multipart / form limits for code & hack submissions (Starlette default is 1MB,
# which is far too small for large hack inputs). Newer Starlette reads the limit from a
# keyword-argument default rather than a class attribute, so we patch the constructors.
MAX_FORM_PART = 64 * 1024 * 1024   # 64MB
import starlette.formparsers as _fp

_MPP = _fp.MultiPartParser
_MPP.spool_max_size = MAX_FORM_PART
_MPP.max_part_size = MAX_FORM_PART
_MPP.max_file_size = MAX_FORM_PART

def _patch_parser(cls):
    _orig = cls.__init__
    def __init__(self, *a, **kw):
        kw["max_part_size"] = MAX_FORM_PART
        _orig(self, *a, **kw)
    cls.__init__ = __init__

_patch_parser(_fp.MultiPartParser)
_patch_parser(_fp.FormParser)

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, init_db, hash_password, verify_password, create_session, user_from_token
from judge import judge_submission, evaluate_hack

BASE = Path(__file__).parent
STATIC = BASE / "static"
TEMPLATES = BASE / "templates"

app = FastAPI(title="OIL OJ")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

# Background judge queue
JUDGE_QUEUE: asyncio.Queue = asyncio.Queue()
HACK_QUEUE: asyncio.Queue = asyncio.Queue()

# ---------- context: current user ----------
async def current_user(request: Request):
    token = request.cookies.get("oj_token")
    if not token:
        # also allow header
        auth = request.headers.get("Authorization","")
        if auth.startswith("Bearer "):
            token = auth[7:]
    db = await get_db()
    try:
        u = await user_from_token(db, token)
        return u
    finally:
        await db.close()

def must_login(user):
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user

# ---------- helpers ----------
async def fetch_problem(db, pid):
    row = await db.execute("SELECT * FROM problems WHERE id=?", (pid,))
    p = await row.fetchone()
    if not p: return None
    d = dict(p)
    d["subtasks"] = json.loads(d["subtasks"] or "[]")
    try:
        d["sample_groups"] = json.loads(d.get("sample_groups") or "[]")
    except Exception:
        d["sample_groups"] = []
    return d

async def fetch_contest(db, cid):
    row = await db.execute("SELECT * FROM contests WHERE id=?", (cid,))
    c = await row.fetchone()
    if not c: return None
    d = dict(c)
    # problems
    # NOTE: `p.*` must come last and `cp.id` must be excluded, otherwise the
    # contest_problems row id shadows the problem id and every lookup breaks.
    cur = await db.execute(
        "SELECT cp.slot AS slot, p.* FROM contest_problems cp "
        "JOIN problems p ON p.id=cp.problem_id WHERE cp.contest_id=?", (cid,))
    rows = await cur.fetchall()
    d["problems"] = {}
    for r in rows:
        pd = dict(r)
        pd["subtasks"] = json.loads(pd["subtasks"] or "[]")
        d["problems"][pd["slot"]] = pd
    return d

def contest_phase(contest, now=None):
    now = now if now is not None else time.time()
    start = contest["start_time"]
    solve_end = start + contest["solve_duration"]
    hack_end = solve_end + contest["hack_duration"]
    if now < start: return "before"
    if now < solve_end: return "solve"
    if now < hack_end: return "hack"
    return "after"

def phase_remaining(contest, now=None):
    now = now if now is not None else time.time()
    start = contest["start_time"]
    solve_end = start + contest["solve_duration"]
    hack_end = solve_end + contest["hack_duration"]
    ph = contest_phase(contest, now)
    if ph == "before": return int(start - now)
    if ph == "solve": return int(solve_end - now)
    if ph == "hack": return int(hack_end - now)
    return 0

async def is_locked(db, contest_id, user_id):
    row = await db.execute("SELECT 1 FROM personal_locks WHERE contest_id=? AND user_id=?", (contest_id, user_id))
    return await row.fetchone() is not None


def is_admin(user):
    return bool(user and user["is_admin"])


def require_admin(user):
    if not is_admin(user):
        raise HTTPException(403, "需要管理员权限")
    return user


def is_author(user, problem):
    """True when `user` created this problem.

    Matches on author_id (stamped at creation), falling back to the author name
    for rows written before author_id existed.
    """
    if not user or not problem:
        return False
    try:
        aid = problem["author_id"]
    except (KeyError, IndexError, TypeError):
        aid = None
    if aid and aid == user["id"]:
        return True
    try:
        aname = (problem["author"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return False
    if not aname:
        return False
    return aname in ((user["display_name"] or "").strip(), (user["username"] or "").strip())


# ---------------------------------------------------------------------------
# Contest managers (出题负责人)
# ---------------------------------------------------------------------------
# A manager is appointed by an admin for a specific contest. They may create and
# edit problems, upload test data and configure the SPJ, but they must NOT be
# able to touch team composition / user assignment — that stays admin-only.

async def managed_contest_ids(db, user):
    if not user:
        return []
    cur = await db.execute("SELECT contest_id FROM contest_managers WHERE user_id=?", (user["id"],))
    return [r["contest_id"] for r in await cur.fetchall()]


async def is_manager(db, user):
    """True if the user manages at least one contest."""
    if is_admin(user):
        return True
    return bool(await managed_contest_ids(db, user))


async def require_problem_editor(db, user):
    """Admins and contest managers may both author problems and data."""
    if is_admin(user):
        return "admin"
    if user and await managed_contest_ids(db, user):
        return "manager"
    raise HTTPException(403, "需要管理员或出题负责人权限")


async def require_console_access(db, user):
    """Who may open the management console at all.

    Besides admins and contest managers, anyone who has authored at least one
    problem needs access so they can find and edit their own work.
    """
    if is_admin(user):
        return "admin"
    if user and await managed_contest_ids(db, user):
        return "manager"
    raise HTTPException(403, "需要管理员或出题负责人权限")


async def require_problem_owner(db, user, pid):
    """Edit rights for ONE specific problem.

    Only admins and the problem's author may edit. Contest managers cannot edit
    other people's problems (public or private).
    """
    if is_admin(user):
        return "admin"
    if user:
        p = await fetch_problem(db, pid)
        if p and is_author(user, p):
            return "author"
    raise HTTPException(403, "只能编辑自己创建的题目")


async def require_contest_editor(db, user, cid):
    """Edit rights for one specific contest."""
    if is_admin(user):
        return "admin"
    if user and cid in await managed_contest_ids(db, user):
        return "manager"
    raise HTTPException(403, "你不是该比赛的负责人")


# ---------------------------------------------------------------------------
# Problem visibility
# ---------------------------------------------------------------------------
# A problem may belong to any number of contests. Rules:
#   * admin                      -> sees everything, always, with difficulty
#   * problem.is_public          -> publicly listed & readable outside contests
#   * used by a contest that has ENDED -> becomes publicly readable, difficulty
#     revealed, and hack data is published
#   * contest not started        -> completely invisible (even the title)
#   * contest running            -> OIL isolation rules decide; difficulty HIDDEN
#
# Returns a dict describing what the viewer may do with this problem.

async def problem_contest_links(db, pid):
    """All contests that include this problem: [(contest_row, slot), ...]"""
    cur = await db.execute(
        "SELECT c.*, cp.slot FROM contest_problems cp JOIN contests c ON c.id=cp.contest_id "
        "WHERE cp.problem_id=?", (pid,))
    return [dict(r) for r in await cur.fetchall()]


async def problem_visibility(db, problem, viewer, contest_id=None):
    """Decide whether `viewer` may see this problem, and whether difficulty is revealed.

    Returns {"visible", "reveal_difficulty", "reveal_hack_data", "reason", "context"}.
    """
    pid = problem["id"]
    if is_admin(viewer):
        return {"visible": True, "reveal_difficulty": True, "reveal_hack_data": True,
                "reason": "admin", "context": "admin"}

    # 作者只能看见自己的题（含未公开），看不到别人的私有题。
    if is_author(viewer, problem):
        return {"visible": True, "reveal_difficulty": True, "reveal_hack_data": True,
                "reason": "author", "context": "author"}

    links = await problem_contest_links(db, pid)

    # If any contest containing this problem has finished, the problem is released:
    # public, difficulty shown, hack data published.
    for lk in links:
        if contest_phase(lk) == "after":
            return {"visible": True, "reveal_difficulty": True, "reveal_hack_data": True,
                    "reason": "contest_ended", "context": "released"}

    # Explicit contest context -> OIL isolation rules.
    if contest_id:
        link = next((l for l in links if l["id"] == contest_id), None)
        if link:
            phase = contest_phase(link)
            slot = link["slot"]
            if phase == "before":
                return {"visible": False, "reveal_difficulty": False, "reveal_hack_data": False,
                        "reason": "比赛尚未开始", "context": "contest"}
            locked = bool(viewer and await is_locked(db, contest_id, viewer["id"]))
            if slot and slot.startswith("personal:"):
                pos = int(slot.split(":")[1])
                own = bool(viewer and viewer["position"] == pos)
                ok = own or locked
                return {"visible": ok, "reveal_difficulty": False, "reveal_hack_data": False,
                        "reason": "" if ok else "你只能查看自己的个人题（锁题后可查看对方同位置个人题）",
                        "context": "contest"}
            # 公开 Hack 阶段未锁题也可看团队题以便提交拿 Hack 资格
            ok = locked or (phase == "hack" and bool(viewer and viewer["team_id"]))
            return {"visible": ok, "reveal_difficulty": False, "reveal_hack_data": False,
                    "reason": "" if ok else "锁题后才能查看团队题", "context": "contest"}

    # No explicit contest context. A problem that is scheduled in a not-yet-finished
    # contest stays hidden from the public list even if flagged public, otherwise
    # contestants could preview it early.
    in_pending_contest = any(contest_phase(l) != "after" for l in links)
    if problem["is_public"] and not in_pending_contest:
        return {"visible": True, "reveal_difficulty": True, "reveal_hack_data": False,
                "reason": "", "context": "public"}

    # ...but a contestant must still reach their own live-contest problems from the
    # normal problem list, so fall back to per-contest rules for running contests.
    for lk in links:
        if contest_phase(lk) in ("solve", "hack"):
            sub = await problem_visibility(db, problem, viewer, lk["id"])
            if sub["visible"]:
                sub["context"] = "contest"
                return sub

    if in_pending_contest:
        return {"visible": False, "reveal_difficulty": False, "reveal_hack_data": False,
                "reason": "该题属于未结束的比赛，暂不公开", "context": "contest"}
    return {"visible": False, "reveal_difficulty": False, "reveal_hack_data": False,
            "reason": "该题目未公开", "context": "private"}


def strip_problem(problem, vis):
    """Remove fields the viewer is not allowed to see."""
    d = dict(problem)
    if not vis["reveal_difficulty"]:
        d["difficulty"] = ""
    if not vis["reveal_hack_data"]:
        d.pop("validator", None)
    return d

async def compute_oil_state(db, contest, viewer=None):
    """Compute the full OIL contest state: locks, problems visibility, scores, hacks, messages."""
    cid = contest["id"]
    now = time.time()
    phase = contest_phase(contest, now)

    # members
    cur = await db.execute("SELECT u.*, t.name as team_name, t.color as team_color FROM users u LEFT JOIN teams t ON t.id=u.team_id WHERE u.team_id IS NOT NULL ORDER BY u.team_id, u.position")
    members = [dict(r) for r in await cur.fetchall()]

    # locks
    cur = await db.execute("SELECT user_id, locked_at FROM personal_locks WHERE contest_id=?", (cid,))
    lock_map = {r["user_id"]: r["locked_at"] for r in await cur.fetchall()}

    # best submissions per user per problem
    cur = await db.execute(
        "SELECT s.* FROM submissions s WHERE s.contest_id=? ORDER BY s.id DESC", (cid,))
    subs = [dict(r) for r in await cur.fetchall()]
    best = {}  # (uid, pid) -> submission dict
    for s in subs:
        key = (s["user_id"], s["problem_id"])
        if key not in best or s["score"] > best[key]["score"]:
            best[key] = s

    # hacks
    cur = await db.execute("SELECT * FROM hacks WHERE contest_id=? ORDER BY id DESC", (cid,))
    hacks = [dict(r) for r in await cur.fetchall()]
    # successful hacks per (target, problem, subtask)
    hacked_personal = set()
    hacked_team = set()  # (target_team, problem)
    for h in hacks:
        if h["status"] != "SUCCESS": continue
        if h["kind"] == "personal":
            idxs = json.loads(h["subtask_indices"] or "[]")
            for i in idxs:
                hacked_personal.add((h["target_id"], h["problem_id"], i))
        else:
            hacked_team.add((h["target_team_id"], h["problem_id"]))

    problems = contest["problems"]

    # visibility
    viewer_locked = viewer and viewer["id"] in lock_map
    viewer_team = viewer["team_id"] if viewer else None
    viewer_pos = viewer["position"] if viewer else None

    hide_names = phase == "before"
    def pub_title(p):
        return "" if hide_names else p["title"]

    # Build problem list with visibility info for the viewer
    visible_problems = []
    for slot, p in sorted(problems.items()):
        if slot.startswith("personal:"):
            pos = int(slot.split(":")[1])
            is_own = viewer and viewer_pos == pos
            can_see = bool(not hide_names and (is_own or (viewer_locked and phase in ("solve","hack"))))
            # 做题阶段 / 公开 Hack：未锁题可提交自己的个人题；已锁题不能再交
            can_submit = bool(is_own and not viewer_locked and phase in ("solve", "hack"))
            visible_problems.append({
                "slot": slot, "id": p["id"], "title": pub_title(p), "type": p["problem_type"],
                "score_total": p["score_total"], "position": pos,
                "visible": can_see, "can_submit": can_submit, "is_own": bool(is_own),
                "subtasks": p["subtasks"],
            })
        else:
            # 做题阶段锁题后可见；公开 Hack 阶段未锁题也可看（以便提交拿 Hack 资格）
            can_see = bool(not hide_names and (
                (viewer_locked and phase in ("solve", "hack"))
                or (phase == "hack" and viewer and viewer_team)
            ))
            can_submit = bool(
                (can_see and phase == "solve" and viewer_locked)
                or (phase == "hack" and viewer and viewer_team and not viewer_locked)
            )
            visible_problems.append({
                "slot": slot, "id": p["id"], "title": pub_title(p), "type": p["problem_type"],
                "score_total": p["score_total"], "visible": can_see, "can_submit": can_submit,
                "subtasks": p["subtasks"],
            })

    # Compute scores
    # personal scores: per user, per personal problem; each subtask *0.4 if hacked
    personal_scores = {}
    for m in members:
        uid = m["id"]
        slot = f"personal:{m['position']}"
        p = problems.get(slot)
        if not p: continue
        s = best.get((uid, p["id"]))
        raw = [0]*len(p["subtasks"])
        if s and s["subtask_scores"]:
            raw = list(json.loads(s["subtask_scores"]))
        eff = []
        for i, st in enumerate(p["subtasks"]):
            got = raw[i] if i < len(raw) else 0
            if got and (uid, p["id"], i) in hacked_personal:
                got = int(got * 0.4)
            eff.append(got)
        personal_scores[uid] = {"raw": raw, "eff": eff, "total": sum(eff), "submitted": s is not None}

    # team scores: per team, per team problem; team score = 50 if any member AC; if hacked, 30% kept, attacker gains 70%
    team_problem_score = {}   # (team, pid) -> score
    team_solvers = {}         # (team, pid) -> list of uids who AC
    for slot, p in problems.items():
        if not slot.startswith("team:") and slot != "mystery": continue
        pid = p["id"]
        for t in set(m["team_id"] for m in members):
            solvers = []
            for m in members:
                if m["team_id"] != t: continue
                s = best.get((m["id"], pid))
                if s and s["score"] and s["score"] >= p["score_total"]:
                    solvers.append(m["id"])
            team_solvers[(t, pid)] = solvers
            base = p["score_total"] if solvers else 0
            if base and (t, pid) in hacked_team and p["problem_type"] != "mystery":
                base = int(base * 0.3)
            team_problem_score[(t, pid)] = base

    # attacker gains from team hacks (70% of victim's full problem score)
    attacker_gains = {}
    for h in hacks:
        if h["kind"] == "team" and h["status"] == "SUCCESS":
            p = problems  # resolve pid
            pid = h["problem_id"]
            full = None
            for slot, pp in problems.items():
                if pp["id"] == pid: full = pp["score_total"]; break
            if full:
                attacker_gains[h["attacker_id"]] = attacker_gains.get(h["attacker_id"],0) + int(full*0.7)

    # team totals
    team_totals = {}
    for t in set(m["team_id"] for m in members):
        total = 0
        for (tt, pid), sc in team_problem_score.items():
            if tt == t: total += sc
        for m in members:
            if m["team_id"] == t:
                total += personal_scores.get(m["id"],{}).get("total",0)
        # add gains from attackers on this team
        for m in members:
            if m["team_id"] == t:
                total += attacker_gains.get(m["id"],0)
        team_totals[t] = total

    # ---- team chat ----------------------------------------------------------
    # Players see only their own team's channel, and only once locked. Admins and
    # the contest's managers supervise BOTH channels (read-only observation).
    messages = []
    all_channels = []
    supervisor = is_admin(viewer) or (
        viewer and cid in await managed_contest_ids(db, viewer))

    if supervisor:
        cur = await db.execute(
            "SELECT tm.*, u.display_name as uname, t.name as team_name, t.color as team_color "
            "FROM team_messages tm JOIN users u ON u.id=tm.user_id "
            "LEFT JOIN teams t ON t.id=tm.team_id WHERE tm.contest_id=? ORDER BY tm.id", (cid,))
        rows = [dict(r) for r in await cur.fetchall()]
        by_team = {}
        for r in rows:
            by_team.setdefault(r["team_id"], []).append(r)
        seen_teams = {}
        for m in members:
            seen_teams.setdefault(m["team_id"], (m["team_name"], m["team_color"]))
        for tid, (tname, tcolor) in seen_teams.items():
            all_channels.append({
                "team_id": tid, "team_name": tname, "team_color": tcolor,
                "messages": by_team.get(tid, []),
            })
        messages = by_team.get(viewer_team, []) if viewer_team else []
    elif viewer and viewer_team:
        can_read = (viewer_locked and phase in ("solve", "hack")) or phase == "after"
        if can_read:
            cur = await db.execute(
                "SELECT tm.*, u.display_name as uname FROM team_messages tm JOIN users u ON u.id=tm.user_id WHERE tm.contest_id=? AND tm.team_id=? ORDER BY tm.id",
                (cid, viewer_team))
            messages = [dict(r) for r in await cur.fetchall()]

    # Can chat: locked and phase solve/hack
    can_chat = bool(viewer_locked and phase in ("solve","hack"))

    # Hack eligibility
    # personal hack: viewer locked, phase solve, target is opponent at same position, can choose subtasks the target scored on
    hack_targets = []
    if viewer and viewer_locked and phase == "solve":
        mypos = viewer_pos
        for m in members:
            if m["team_id"] != viewer_team and m["position"] == mypos:
                slot = f"personal:{mypos}"
                p = problems.get(slot)
                s = best.get((m["id"], p["id"])) if p else None
                scored = []
                if s and int(s.get("locked_submit") or 0) != 1:
                    s = None
                if s and s["subtask_scores"]:
                    raw = json.loads(s["subtask_scores"])
                    for i, st in enumerate(p["subtasks"]):
                        if i < len(raw) and raw[i] > 0:
                            already = (m["id"], p["id"], i) in hacked_personal
                            scored.append({"index": i, "name": st["name"], "score": raw[i], "hacked": already})
                hack_targets.append({
                    "user_id": m["id"], "display_name": m["display_name"],
                    "problem_id": p["id"], "problem_title": p["title"],
                    "scored_subtasks": scored,
                })
    # team hack: phase hack, target is the other team (any problem they solved that is a thinking problem)
    team_hack_targets = []
    if viewer and viewer_team and phase == "hack":
        opp = [t for t in set(m["team_id"] for m in members) if t != viewer_team]
        if opp:
            opp_team = opp[0]
            for slot, p in problems.items():
                if not slot.startswith("team:"): continue  # mystery not hackable
                my_best = best.get((viewer["id"], p["id"])) if viewer else None
                i_ac = bool(my_best and my_best["score"] and my_best["score"] >= p["score_total"])
                # 已锁题：可 Hack 所有对方已锁提交；未锁题：必须自己先 AC 这题
                if not (viewer_locked or i_ac):
                    continue
                solvers = team_solvers.get((opp_team, p["id"]), [])
                # 未锁题时交的代码不能被 Hack
                solvers = [uid for uid in solvers
                           if int((best.get((uid, p["id"])) or {}).get("locked_submit") or 0) == 1]
                already = (opp_team, p["id"]) in hacked_team
                if solvers:
                    codes = []
                    for uid in solvers:
                        s = best.get((uid, p["id"]))
                        m = next((x for x in members if x["id"] == uid), None)
                        codes.append({
                            "user_id": uid,
                            "display_name": m["display_name"] if m else str(uid),
                            "submission_id": s["id"] if s else None,
                            "score": s["score"] if s else 0,
                        })
                    team_hack_targets.append({
                        "problem_id": p["id"], "problem_title": p["title"],
                        "score_total": p["score_total"],
                        "solvers": [c["display_name"] for c in codes],
                        "solver_subs": codes,
                        "hacked": already,
                    })

    return {
        "phase": phase,
        "now": now,
        "start": contest["start_time"],
        "remaining": phase_remaining(contest, now),
        "members": [{
            "id": m["id"], "display_name": m["display_name"], "team_id": m["team_id"],
            "team_name": m["team_name"], "team_color": m["team_color"], "position": m["position"],
            "locked": m["id"] in lock_map, "locked_at": lock_map.get(m["id"]),
            "personal_total": personal_scores.get(m["id"],{}).get("total",0),
            "attacker_gain": attacker_gains.get(m["id"],0),
        } for m in members],
        "locks": {str(k): v for k,v in lock_map.items()},
        "problems": visible_problems,
        "all_problems_summary": [
            {"slot": slot, "id": p["id"],
             "title": ("" if phase == "before" else p["title"]),
             "type": p["problem_type"],
             "score_total": p["score_total"]}
            for slot, p in sorted(problems.items())
        ],
        "team_totals": team_totals,
        "personal_scores": {str(k): v for k,v in personal_scores.items()},
        "team_problem_score": {f"{k[0]}:{k[1]}": v for k,v in team_problem_score.items()},
        "messages": messages,
        "all_channels": all_channels,
        "is_supervisor": bool(supervisor),
        "can_chat": can_chat,
        "hack_targets": hack_targets,
        "team_hack_targets": team_hack_targets,
        "hacks": [{
            "id": h["id"], "attacker_id": h["attacker_id"], "target_id": h["target_id"],
            "problem_id": h["problem_id"], "kind": h["kind"], "status": h["status"],
            "message": h["message"], "subtask_indices": json.loads(h["subtask_indices"] or "[]"),
            "created_at": h["created_at"], "judged_at": h["judged_at"],
        } for h in hacks],
        "viewer_locked": viewer_locked,
        "can_lock": bool(viewer and viewer["team_id"]
                         and viewer["id"] not in lock_map
                         and phase in ("solve", "hack")),
    }

# ============================================================
# PAGE ROUTES
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user=Depends(current_user)):
    return Render("index.html", request, user, active="home")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return Render("login.html", request, None)

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return Render("register.html", request, None)

@app.get("/logout")
async def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("oj_token")
    return resp

@app.get("/problems", response_class=HTMLResponse)
async def problems_page(request: Request, user=Depends(current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM problems ORDER BY id")
        probs = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()
    return Render("problems.html", request, user, active="problems", problems=probs)

@app.get("/problem/{pid}", response_class=HTMLResponse)
async def problem_page(pid: int, request: Request, contest_id: Optional[int] = None,
                       user=Depends(current_user)):
    """Serve the problem page shell.

    The real permission check happens in /api/problem/{id}; the client renders a
    friendly message (with the nav intact) instead of dumping raw JSON.
    """
    db = await get_db()
    try:
        p = await fetch_problem(db, pid)
        if not p:
            raise HTTPException(404, "题目不存在")
        subs = []
        if user:
            cur = await db.execute(
                "SELECT * FROM submissions WHERE user_id=? AND problem_id=? "
                "ORDER BY id DESC LIMIT 20", (user["id"], pid))
            subs = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()
    return Render("problem.html", request, user, active="problems",
                  problem=p, submissions=subs, contest_id=contest_id)

@app.get("/status", response_class=HTMLResponse)
async def status_page(request: Request, user=Depends(current_user)):
    return Render("status.html", request, user, active="status")

@app.get("/contests", response_class=HTMLResponse)
async def contests_page(request: Request, user=Depends(current_user)):
    return Render("contests.html", request, user, active="contests")

@app.get("/contest/{cid}/standings", response_class=HTMLResponse)
async def standings_page(cid: int, request: Request, user=Depends(current_user)):
    return Render("standings.html", request, user, active="contests")

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user=Depends(current_user)):
    return Render("admin.html", request, user, active="admin")

@app.get("/submission/{sid}", response_class=HTMLResponse)
async def submission_page(sid: int, request: Request, user=Depends(current_user)):
    """Full-page submission detail (nicer to read than the inline panel)."""
    return Render("submission.html", request, user, active="status")

@app.get("/admin/problem", response_class=HTMLResponse)
async def admin_problem_new_page(request: Request, user=Depends(current_user)):
    return Render("problem_edit.html", request, user, active="admin")

@app.get("/admin/problem/{pid}", response_class=HTMLResponse)
async def admin_problem_edit_page(pid: int, request: Request, user=Depends(current_user)):
    return Render("problem_edit.html", request, user, active="admin")

@app.get("/contest/{cid}", response_class=HTMLResponse)
async def contest_page(cid: int, request: Request, user=Depends(current_user)):
    db = await get_db()
    try:
        c = await fetch_contest(db, cid)
        if not c: raise HTTPException(404)
    finally:
        await db.close()
    return Render("contest.html", request, user, active="contest", contest=c)

# ============================================================
# API: auth
# ============================================================
def asset_version() -> str:
    """Fingerprint of the local JS/CSS, used to bust the browser cache.

    Without this the browser keeps serving a stale app.js after an upgrade,
    which surfaces as "function is not defined" errors and unstyled pages.
    """
    newest = 0.0
    for f in (STATIC / "app.js", STATIC / "style.css"):
        try:
            newest = max(newest, f.stat().st_mtime)
        except OSError:
            pass
    return str(int(newest))


def Render(template, request, user, **ctx):
    """Serve a template, stamping a version query onto our own static assets."""
    tpath = TEMPLATES / template
    html = tpath.read_text(encoding="utf-8")
    v = asset_version()
    # Only touch first-party assets; vendored libs are immutable and can stay cached.
    html = html.replace('href="/static/style.css"', f'href="/static/style.css?v={v}"')
    html = html.replace('src="/static/app.js"', f'src="/static/app.js?v={v}"')
    return HTMLResponse(html, headers={
        # The HTML shell itself must never be cached, or it would keep pointing
        # at an outdated ?v= and defeat the whole mechanism.
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })

@app.post("/api/login")
async def api_login(username: str = Form(...), password: str = Form(...)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM users WHERE username=?", (username,))
        u = await cur.fetchone()
        if not u or not verify_password(password, u["password_hash"]):
            raise HTTPException(401, "用户名或密码错误")
        token = await create_session(db, u["id"])
        resp = JSONResponse({"ok": True, "user": {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "is_admin": bool(u["is_admin"])}})
        resp.set_cookie("oj_token", token, httponly=True, samesite="lax", max_age=7*86400)
        return resp
    finally:
        await db.close()

@app.post("/api/register")
async def api_register(username: str = Form(...), password: str = Form(...), display_name: str = Form("")):
    if len(username) < 2 or len(password) < 4:
        raise HTTPException(400, "用户名至少2位，密码至少4位")
    db = await get_db()
    try:
        cur = await db.execute("SELECT 1 FROM users WHERE username=?", (username,))
        if await cur.fetchone():
            raise HTTPException(400, "用户名已存在")
        cur = await db.execute(
            "INSERT INTO users(username,password_hash,display_name,created_at) VALUES(?,?,?,?)",
            (username, hash_password(password), display_name or username, time.time()))
        uid = cur.lastrowid
        token = await create_session(db, uid)
        resp = JSONResponse({"ok": True})
        resp.set_cookie("oj_token", token, httponly=True, samesite="lax", max_age=7*86400)
        return resp
    finally:
        await db.close()

@app.get("/api/me")
async def api_me(user=Depends(current_user)):
    if not user: return JSONResponse({"user": None})
    db = await get_db()
    try:
        managed = await managed_contest_ids(db, user)
        cur = await db.execute(
            "SELECT COUNT(*) AS n FROM problems "
            "WHERE author_id=? OR (author<>'' AND author IN (?,?))",
            (user["id"], user["display_name"] or "", user["username"] or ""))
        authored = (await cur.fetchone())["n"]
    finally:
        await db.close()
    return {"user": {"id": user["id"], "username": user["username"],
                     "display_name": user["display_name"], "team_id": user["team_id"],
                     "position": user["position"], "is_admin": bool(user["is_admin"]),
                     "is_manager": bool(managed), "managed_contests": managed,
                     "is_author": bool(authored), "authored_count": authored}}

# ============================================================
# API: problems / submissions
# ============================================================
@app.get("/api/problems")
async def api_problems(contest_id: Optional[int] = None, user=Depends(current_user)):
    """Problem list, filtered by visibility. Difficulty is hidden unless revealed.

    When `contest_id` is given the OIL rules for that contest apply, so a
    contestant sees their own personal problem (and, once locked, the team
    problems) instead of an empty list.
    """
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM problems ORDER BY id")
        rows = [dict(r) for r in await cur.fetchall()]
        my_best = {}
        if user:
            cur = await db.execute(
                "SELECT problem_id, MAX(score) AS best, "
                "SUM(CASE WHEN status NOT IN ('PENDING','JUDGING') THEN 1 ELSE 0 END) AS judged "
                "FROM submissions WHERE user_id=? GROUP BY problem_id",
                (user["id"],))
            for r in await cur.fetchall():
                my_best[r["problem_id"]] = dict(r)
        out = []
        for p in rows:
            vis = await problem_visibility(db, p, user, contest_id)
            if not vis["visible"]:
                continue
            mb = my_best.get(p["id"])
            full = p["score_total"] or 0
            if mb and (mb["best"] or 0) >= full and full > 0:
                attempt = "ac"
            elif mb and (mb["judged"] or 0) > 0:
                attempt = "tried"
            else:
                attempt = "none"
            out.append({
                "id": p["id"], "slug": p["slug"], "title": p["title"],
                "problem_type": p["problem_type"], "score_total": p["score_total"],
                "time_limit": p["time_limit"], "memory_limit": p["memory_limit"],
                "difficulty": p["difficulty"] if vis["reveal_difficulty"] else "",
                "difficulty_hidden": not vis["reveal_difficulty"],
                "tags": p["tags"] or "",
                "is_public": p["is_public"],
                "author": p["author"] or "",
                "attempt": attempt,
                "my_score": (mb["best"] if mb else None),
                "has_std": bool((p.get("std_source") or "").strip()),
            })
        return {"problems": out}
    finally:
        await db.close()

@app.get("/api/problem/{pid}")
async def api_problem(pid: int, contest_id: Optional[int] = None, user=Depends(current_user)):
    db = await get_db()
    try:
        p = await fetch_problem(db, pid)
        if not p: raise HTTPException(404)
        vis = await problem_visibility(db, p, user, contest_id)
        if not vis["visible"]:
            raise HTTPException(403, vis["reason"] or "无权查看该题目")
        out = strip_problem(p, vis)
        out["difficulty_hidden"] = not vis["reveal_difficulty"]
        # After the contest ends, publish the hack data submitted against this problem.
        if vis["reveal_hack_data"]:
            cur = await db.execute(
                "SELECT h.id,h.kind,h.status,h.message,h.input_data,h.created_at,"
                "       ua.display_name AS attacker, ut.display_name AS target "
                "FROM hacks h LEFT JOIN users ua ON ua.id=h.attacker_id "
                "LEFT JOIN users ut ON ut.id=h.target_id "
                "WHERE h.problem_id=? AND h.status IN ('SUCCESS','FAILURE') ORDER BY h.id",
                (pid,))
            out["hack_data"] = [dict(r) for r in await cur.fetchall()]
        return {"problem": out, "visibility": vis}
    finally:
        await db.close()

async def submission_access(db, sub, viewer):
    """How much of `sub` may `viewer` see?

    Returns (can_list, can_detail). `can_detail` covers the source code and the
    per-testcase breakdown; `can_list` is just the row (verdict/score/time).

    Contest rules:
      * your own submissions          -> always full detail
      * admin                         -> always full detail
      * during the solve phase        -> teammates' rows appear only once BOTH
                                         you and they have locked; opponents stay
                                         hidden entirely
      * during the public hack phase  -> contestants may open anyone's source
      * spectators / other users      -> may see the row, never the detail
      * after the contest ends        -> rows public, detail still owner-only
    """
    if viewer and sub["user_id"] == viewer["id"]:
        return True, True
    if is_admin(viewer):
        return True, True

    cid = sub["contest_id"]
    if not cid:
        # Practice submission outside any contest: listed publicly, detail private.
        return True, False

    c = await fetch_contest(db, cid)
    if not c:
        return True, False
    phase = contest_phase(c)

    if phase == "hack":
        # Public hack: contestants may open anyone's source to craft tests.
        # Spectators still only see the verdict row.
        if viewer and viewer["team_id"]:
            return True, True
        return True, False

    if phase == "solve":
        if not viewer:
            return True, False                     # anonymous spectator
        owner = await db.execute("SELECT team_id FROM users WHERE id=?", (sub["user_id"],))
        orow = await owner.fetchone()
        same_team = orow and viewer["team_id"] and orow["team_id"] == viewer["team_id"]
        if same_team:
            # Teammate rows unlock only when both sides have locked their problem.
            both_locked = (await is_locked(db, cid, viewer["id"])
                           and await is_locked(db, cid, sub["user_id"]))
            return (True, True) if both_locked else (False, False)
        if viewer["team_id"]:
            # Opposing contestant: information isolation, nothing at all.
            return False, False
        return True, False                         # logged-in spectator
    return True, False


@app.get("/api/submissions")
async def api_submissions(limit: int = 50, problem_id: Optional[int] = None,
                          user_id: Optional[int] = None, contest_id: Optional[int] = None,
                          user=Depends(current_user)):
    db = await get_db()
    try:
        q = ("SELECT s.id, s.user_id, u.display_name, s.problem_id, p.title as problem_title, "
             "s.status, s.score, s.language, s.created_at, s.contest_id "
             "FROM submissions s JOIN users u ON u.id=s.user_id "
             "JOIN problems p ON p.id=s.problem_id WHERE 1=1")
        args = []
        if problem_id: q += " AND s.problem_id=?"; args.append(problem_id)
        if user_id: q += " AND s.user_id=?"; args.append(user_id)
        if contest_id: q += " AND s.contest_id=?"; args.append(contest_id)
        # Over-fetch, because visibility filtering happens per row below.
        q += " ORDER BY s.id DESC LIMIT ?"; args.append(max(limit * 4, 200))
        cur = await db.execute(q, args)
        rows = []
        for r in await cur.fetchall():
            d = dict(r)
            can_list, can_detail = await submission_access(db, d, user)
            if not can_list:
                continue
            d["can_detail"] = can_detail
            d["kind"] = "submission"
            rows.append(d)
            if len(rows) >= limit:
                break
        return {"submissions": rows}
    finally:
        await db.close()


@app.get("/api/hacks")
async def api_hacks(limit: int = 50, contest_id: Optional[int] = None, user=Depends(current_user)):
    """Hack records, shaped like submissions so the status table can merge them."""
    db = await get_db()
    try:
        q = ("SELECT h.id, h.contest_id, h.problem_id, h.attacker_id, h.target_id, h.kind, "
             "h.status, h.message, h.created_at, h.judged_at, "
             "p.title AS problem_title, ua.display_name AS attacker_name, "
             "ut.display_name AS target_name "
             "FROM hacks h JOIN problems p ON p.id=h.problem_id "
             "LEFT JOIN users ua ON ua.id=h.attacker_id "
             "LEFT JOIN users ut ON ut.id=h.target_id WHERE 1=1")
        args = []
        if contest_id: q += " AND h.contest_id=?"; args.append(contest_id)
        q += " ORDER BY h.id DESC LIMIT ?"; args.append(limit)
        cur = await db.execute(q, args)
        out = []
        for r in await cur.fetchall():
            d = dict(r)
            # Anyone may see that a hack happened and its verdict; the input data
            # and run details are gated in /api/hack/{id}.
            d["kind_label"] = "个人 Hack" if d["kind"] == "personal" else "团队 Hack"
            d["can_detail"] = bool(
                is_admin(user) or (user and user["id"] in (d["attacker_id"], d["target_id"])))
            out.append(d)
        return {"hacks": out}
    finally:
        await db.close()


@app.get("/api/hack/{hid}")
async def api_hack_detail(hid: int, user=Depends(current_user)):
    """Full hack report: std / attacker / victim runs, timings, memory, checker."""
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT h.*, p.title AS problem_title, p.time_limit, p.memory_limit, "
            "ua.display_name AS attacker_name, ut.display_name AS target_name "
            "FROM hacks h JOIN problems p ON p.id=h.problem_id "
            "LEFT JOIN users ua ON ua.id=h.attacker_id "
            "LEFT JOIN users ut ON ut.id=h.target_id WHERE h.id=?", (hid,))
        h = await cur.fetchone()
        if not h: raise HTTPException(404)
        d = dict(h)
        try:
            d["detail"] = json.loads(d.get("detail") or "{}")
        except Exception:
            d["detail"] = {}

        involved = bool(user and user["id"] in (d["attacker_id"], d["target_id"]))
        c = await fetch_contest(db, d["contest_id"]) if d["contest_id"] else None
        ended = (contest_phase(c) == "after") if c else True

        if not (is_admin(user) or involved or ended):
            # Outsiders during a live contest only learn the verdict.
            d.pop("input_data", None)
            d["detail"] = {}
            d["restricted"] = True
        else:
            # Never ship megabytes of hack input to the browser.
            if d.get("input_data") and len(d["input_data"]) > 20000:
                d["input_data"] = d["input_data"][:20000] + "\n...（已截断）"
        return d
    finally:
        await db.close()


@app.get("/api/hack/{hid}/stream")
async def api_hack_stream(hid: int, request: Request):
    """SSE: push the hack verdict as soon as judging finishes."""
    async def gen():
        last = None
        for _ in range(600):
            if await request.is_disconnected():
                break
            db = await get_db()
            try:
                cur = await db.execute("SELECT id,status,message,judged_at FROM hacks WHERE id=?", (hid,))
                row = await cur.fetchone()
            finally:
                await db.close()
            if not row:
                break
            d = dict(row)
            payload = json.dumps(d, ensure_ascii=False, default=str)
            if payload != last:
                last = payload
                yield f"data: {payload}\n\n"
            if d["status"] not in ("PENDING", "JUDGING"):
                yield "event: done\ndata: {}\n\n"
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})

@app.get("/api/submission/{sid}")
async def api_submission(sid: int, user=Depends(current_user)):
    db = await get_db()
    try:
        cur = await db.execute("SELECT s.*, u.display_name, p.title as problem_title FROM submissions s JOIN users u ON u.id=s.user_id JOIN problems p ON p.id=s.problem_id WHERE s.id=?", (sid,))
        s = await cur.fetchone()
        if not s: raise HTTPException(404)
        d = dict(s)
        can_list, can_detail = await submission_access(db, d, user)
        if not can_list:
            raise HTTPException(403, "比赛期间不能查看该提交")
        d["subtask_scores"] = json.loads(d["subtask_scores"] or "[]")
        d["case_results"] = json.loads(d["case_results"] or "[]")
        d["can_detail"] = can_detail
        if not can_detail:
            # Verdict and score stay public; source code and per-case data do not.
            d.pop("code", None)
            d["case_results"] = []
            d["verdict_detail"] = ""
            d["restricted"] = True
        return d
    finally:
        await db.close()

@app.get("/api/submission/{sid}/stream")
async def api_submission_stream(sid: int, request: Request, user=Depends(current_user)):
    """Server-sent events: push this submission's verdict the moment it changes.

    Replaces client-side polling so results appear instantly on the submit page.
    """
    async def gen():
        last = None
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            db = await get_db()
            try:
                cur = await db.execute(
                    "SELECT s.*, p.title AS problem_title FROM submissions s "
                    "JOIN problems p ON p.id=s.problem_id WHERE s.id=?", (sid,))
                s = await cur.fetchone()
            finally:
                await db.close()
            if not s:
                yield "event: error\ndata: {}\n\n"
                break
            d = dict(s)
            d["subtask_scores"] = json.loads(d["subtask_scores"] or "[]")
            d["case_results"] = json.loads(d["case_results"] or "[]")
            d.pop("code", None)
            # Apply the same isolation rules as the REST endpoint.
            db2 = await get_db()
            try:
                can_list, can_detail = await submission_access(db2, d, user)
            finally:
                await db2.close()
            if not can_list:
                yield "event: error\ndata: {}\n\n"
                break
            if not can_detail:
                d["case_results"] = []
                d["verdict_detail"] = ""
                d["restricted"] = True
            payload = json.dumps(d, ensure_ascii=False, default=str)
            if payload != last:
                last = payload
                yield f"data: {payload}\n\n"
            if d["status"] not in ("PENDING", "JUDGING"):
                yield "event: done\ndata: {}\n\n"
                break
            idle += 1
            if idle > 600:            # ~5 min safety valve
                break
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


@app.post("/api/submit")
async def api_submit(problem_id: int = Form(...), code: str = Form(...), contest_id: Optional[int] = Form(None), user=Depends(current_user)):
    must_login(user)
    if not code or len(code) > 100000:
        raise HTTPException(400, "代码为空或过长")
    db = await get_db()
    try:
        p = await fetch_problem(db, problem_id)
        if not p: raise HTTPException(404, "题目不存在")
        # If contest submission, enforce rules
        c = None
        if contest_id:
            c = await fetch_contest(db, contest_id)
            if not c: raise HTTPException(404, "比赛不存在")
            phase = contest_phase(c)
            if phase not in ("solve", "hack"):
                raise HTTPException(403, "当前阶段不能提交")
            slot_for_pid = None
            for slot, pp in c["problems"].items():
                if pp["id"] == problem_id: slot_for_pid = slot; break
            if not slot_for_pid:
                raise HTTPException(403, "该题不在比赛中")
            locked = await is_locked(db, contest_id, user["id"])
            if slot_for_pid.startswith("personal:"):
                pos = int(slot_for_pid.split(":")[1])
                if pos != user["position"]:
                    raise HTTPException(403, "这不是你的个人题")
                if locked:
                    raise HTTPException(403, "你已锁题，不能再提交个人题")
            else:
                if phase == "solve" and not locked:
                    raise HTTPException(403, "未锁题不能查看/提交团队题")
                if phase == "hack" and locked:
                    raise HTTPException(403, "公开 Hack 阶段仅未锁题选手可以继续提交")
        # 没有显式 contest_id 时，自动挂到该题正在进行的比赛，否则榜上分数一直是 0
        if not contest_id:
            links = await problem_contest_links(db, problem_id)
            for lk in links:
                if contest_phase(lk) in ("solve", "hack"):
                    contest_id = lk["id"]
                    break
        locked_flag = 0
        if contest_id:
            locked_flag = 1 if await is_locked(db, contest_id, user["id"]) else 0
        cur = await db.execute(
            "INSERT INTO submissions(user_id,problem_id,contest_id,code,language,status,created_at,locked_submit) VALUES(?,?,?,?,?,?,?,?)",
            (user["id"], problem_id, contest_id, code, "C++20", "PENDING", time.time(), locked_flag))
        sid = cur.lastrowid
        await db.commit()
        await JUDGE_QUEUE.put(sid)
        return {"ok": True, "submission_id": sid}
    finally:
        await db.close()

# ============================================================
# API: contest
# ============================================================
@app.get("/api/contests")
async def api_contests(user=Depends(current_user)):
    """List contests. Unpublished ones are admin-only."""
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM contests ORDER BY start_time DESC, id DESC")
        out = []
        for r in await cur.fetchall():
            c = dict(r)
            if not c["is_published"] and not is_admin(user):
                continue
            c["phase"] = contest_phase(c)
            c["remaining"] = phase_remaining(c)
            cur2 = await db.execute(
                "SELECT COUNT(*) AS n FROM contest_problems WHERE contest_id=?", (c["id"],))
            c["problem_count"] = (await cur2.fetchone())["n"]
            out.append(c)
        return {"contests": out}
    finally:
        await db.close()


def contest_end_ts(contest):
    return contest["start_time"] + contest["solve_duration"] + contest["hack_duration"]


async def record_snapshot(db, contest, state):
    """Append a scoreboard sample, used to draw the score-over-time chart."""
    cid = contest["id"]
    if contest_phase(contest) not in ("solve", "hack"):
        return
    payload = {
        "teams": {str(k): v for k, v in state["team_totals"].items()},
        "users": {str(m["id"]): m["personal_total"] + m["attacker_gain"]
                  for m in state["members"]},
    }
    blob = json.dumps(payload, ensure_ascii=False)
    cur = await db.execute(
        "SELECT payload, ts FROM score_snapshots WHERE contest_id=? ORDER BY id DESC LIMIT 1", (cid,))
    last = await cur.fetchone()
    now = time.time()
    # only store when something actually changed, or every 60s to keep the line moving
    if last and last["payload"] == blob and now - last["ts"] < 60:
        return
    await db.execute("INSERT INTO score_snapshots(contest_id,ts,payload) VALUES(?,?,?)",
                     (cid, now, blob))
    await db.commit()


@app.get("/api/contest/{cid}/standings")
async def api_standings(cid: int, user=Depends(current_user)):
    """Live standings plus the historical series for the score chart."""
    db = await get_db()
    try:
        c = await fetch_contest(db, cid)
        if not c: raise HTTPException(404)
        state = await compute_oil_state(db, c, user)
        end_ts = contest_end_ts(c)
        cur = await db.execute(
            "SELECT ts,payload FROM score_snapshots WHERE contest_id=? AND ts<=? ORDER BY ts",
            (cid, end_ts + 0.5))
        series = []
        for r in await cur.fetchall():
            try:
                series.append({"ts": r["ts"], **json.loads(r["payload"])})
            except Exception:
                pass
        # 比赛进行中才补「此刻」；结束后折线停在最后一次有效采样
        if state["phase"] in ("solve", "hack"):
            series.append({
                "ts": time.time(),
                "teams": {str(k): v for k, v in state["team_totals"].items()},
                "users": {str(m["id"]): m["personal_total"] + m["attacker_gain"]
                          for m in state["members"]},
            })
        teams = {}
        for m in state["members"]:
            teams.setdefault(m["team_id"], {
                "id": m["team_id"], "name": m["team_name"], "color": m["team_color"],
                "total": state["team_totals"].get(m["team_id"], 0), "members": []})
            teams[m["team_id"]]["members"].append(m)
        return {"phase": state["phase"], "remaining": state["remaining"],
                "start": state["start"],
                "teams": sorted(teams.values(), key=lambda t: -t["total"]),
                "team_problem_score": state["team_problem_score"],
                "problems": state["all_problems_summary"],
                "series": series}
    finally:
        await db.close()


@app.get("/api/contest/{cid}")
async def api_contest(cid: int, user=Depends(current_user)):
    db = await get_db()
    try:
        c = await fetch_contest(db, cid)
        if not c: raise HTTPException(404)
        state = await compute_oil_state(db, c, user)
        c["state"] = state
        # don't leak full problem descriptions here; frontend fetches problem detail
        c.pop("problems", None)
        return c
    finally:
        await db.close()

@app.post("/api/contest/{cid}/lock")
async def api_lock(cid: int, user=Depends(current_user)):
    must_login(user)
    db = await get_db()
    try:
        c = await fetch_contest(db, cid)
        if not c: raise HTTPException(404)
        phase = contest_phase(c)
        if phase not in ("solve", "hack"):
            raise HTTPException(403, "只有做题阶段或公开 Hack 阶段可以锁题")
        if not user["team_id"]:
            raise HTTPException(403, "你尚未被分配队伍，无法锁题。请联系管理员将你加入参赛队伍。")
        if await is_locked(db, cid, user["id"]):
            raise HTTPException(400, "你已经锁题")
        await db.execute("INSERT INTO personal_locks(contest_id,user_id,locked_at) VALUES(?,?,?)",
                         (cid, user["id"], time.time()))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@app.post("/api/contest/{cid}/message")
async def api_message(cid: int, message: str = Form(...), user=Depends(current_user)):
    must_login(user)
    if not message.strip() or len(message) > 1000:
        raise HTTPException(400, "消息为空或过长")
    db = await get_db()
    try:
        c = await fetch_contest(db, cid)
        if not c: raise HTTPException(404)
        phase = contest_phase(c)
        locked = await is_locked(db, cid, user["id"])
        if not (locked and phase in ("solve","hack")):
            raise HTTPException(403, "当前不能发言")
        await db.execute(
            "INSERT INTO team_messages(contest_id,team_id,user_id,message,created_at) VALUES(?,?,?,?,?)",
            (cid, user["team_id"], user["id"], message.strip(), time.time()))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@app.get("/api/contest/{cid}/stream")
async def api_stream(cid: int, request: Request, user=Depends(current_user)):
    """SSE stream of contest state updates."""
    async def gen():
        last = 0
        while True:
            if await request.is_disconnected():
                break
            db = await get_db()
            try:
                c = await fetch_contest(db, cid)
                if not c:
                    break
                state = await compute_oil_state(db, c, user)
                try:
                    await record_snapshot(db, c, state)
                except Exception:
                    pass
                payload = json.dumps(state, ensure_ascii=False, default=str)
                yield f"data: {payload}\n\n"
            finally:
                await db.close()
            await asyncio.sleep(3)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ============================================================
# API: hacks
# ============================================================
@app.post("/api/hack")
async def api_hack(
    contest_id: int = Form(...),
    target_id: int = Form(...),
    problem_id: int = Form(...),
    kind: str = Form(...),
    subtask_indices: str = Form(""),
    input_data: str = Form(...),
    user=Depends(current_user),
):
    must_login(user)
    if not input_data or len(input_data) > 16_000_000:
        raise HTTPException(400, "Hack 输入为空或过长（上限 16MB）")
    db = await get_db()
    try:
        c = await fetch_contest(db, contest_id)
        if not c: raise HTTPException(404)
        phase = contest_phase(c)
        locked = await is_locked(db, contest_id, user["id"])
        if not locked:
            raise HTTPException(403, "未锁题不能 Hack")
        if kind == "personal":
            if phase != "solve":
                raise HTTPException(403, "个人题只能在做题阶段 Hack")
            # target must be opponent at same position
            tgt = await db.execute("SELECT * FROM users WHERE id=?", (target_id,))
            t = await tgt.fetchone()
            if not t or t["team_id"] == user["team_id"] or t["position"] != user["position"]:
                raise HTTPException(403, "只能 Hack 对方同位置选手")
            # Accept both a JSON array ("[0,1]") and a comma-separated list ("0,1")
            raw = (subtask_indices or "").strip()
            try:
                idxs = json.loads(raw) if raw.startswith("[") else (
                    [int(x) for x in raw.replace(" ", "").split(",") if x != ""] if raw else []
                )
            except Exception:
                raise HTTPException(400, "子任务列表格式错误")
            if not isinstance(idxs, list):
                idxs = []
            if not idxs:
                raise HTTPException(400, "请选择至少一个子任务")
            target_team = t["team_id"]
            cur = await db.execute(
                """INSERT INTO hacks(contest_id,attacker_id,target_id,target_team_id,problem_id,kind,subtask_indices,input_data,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (contest_id, user["id"], target_id, target_team, problem_id, "personal",
                 json.dumps(idxs), input_data, "PENDING", time.time()))
        elif kind == "team":
            if phase != "hack":
                raise HTTPException(403, "团队题只能在公开 Hack 阶段 Hack")
            tgt = await db.execute("SELECT team_id FROM users WHERE id=?", (target_id,))
            tr = await tgt.fetchone()
            if not tr or tr["team_id"] == user["team_id"]:
                raise HTTPException(403, "目标无效")
            p = await fetch_problem(db, problem_id)
            if not p or p["problem_type"] != "thinking":
                raise HTTPException(403, "只能 Hack 思维题（神秘题禁止 Hack）")
            if not locked:
                cur = await db.execute(
                    "SELECT MAX(score) AS best FROM submissions WHERE user_id=? AND problem_id=? AND contest_id=?",
                    (user["id"], problem_id, contest_id))
                row = await cur.fetchone()
                if not row or (row["best"] or 0) < (p["score_total"] or 0):
                    raise HTTPException(403, "未锁题需先 AC 该题才能 Hack")
            target_team = tr["team_id"]
            cur = await db.execute(
                """INSERT INTO hacks(contest_id,attacker_id,target_id,target_team_id,problem_id,kind,subtask_indices,input_data,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (contest_id, user["id"], target_id, target_team, problem_id, "team",
                 "[]", input_data, "PENDING", time.time()))
        else:
            raise HTTPException(400, "未知类型")
        hid = cur.lastrowid
        await db.commit()
        await HACK_QUEUE.put(hid)
        return {"ok": True, "hack_id": hid}
    finally:
        await db.close()

# ============================================================
# Admin
# ============================================================
DIFFICULTIES = ["入门", "普及-", "普及", "普及+", "提高", "提高+", "省选", "NOI-", "NOI", "NOI+"]

# Skeleton handed to the admin UI when authoring a special judge.
SPJ_TEMPLATE = r"""#include "testlib.h"
#include <cmath>

// 特殊评测 (SPJ) —— 使用 testlib 编写
// 调用约定: spj <input> <output> <answer>
//   inf  = 选手看到的输入      ouf = 选手的输出      ans = 标准答案
// 判定结果通过 quitf 返回:
//   quitf(_ok,  "...")  通过
//   quitf(_wa,  "...")  答案错误
//   quitf(_pe,  "...")  格式错误
// 下面是一个「允许 1e-6 误差的实数比较」示例，请按题目需要修改。

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    double ja = ans.readDouble();
    double pa = ouf.readDouble();

    if (std::fabs(ja - pa) <= 1e-6) {
        quitf(_ok, "answer is correct: %.10f", pa);
    } else {
        quitf(_wa, "expected %.10f, found %.10f", ja, pa);
    }
}
"""


@app.get("/api/admin/overview")
async def admin_overview(user=Depends(current_user)):
    """Everything the admin console needs in one request.

    Contest managers get the same problem/contest data (so they can prepare
    problems) but no user/team management surface.
    """
    db = await get_db()
    try:
        role = await require_console_access(db, user)
        managed = await managed_contest_ids(db, user)
        cur = await db.execute("SELECT * FROM problems ORDER BY id")
        problems = []
        for r in await cur.fetchall():
            d = dict(r)
            mine = is_author(user, d)
            public = bool(d.get("is_public"))
            if role != "admin":
                if not mine and not public:
                    continue
            sts = json.loads(d["subtasks"] or "[]")
            d["subtask_count"] = len(sts)
            d["case_count"] = sum(len(st.get("testcases", [])) for st in sts)
            d.pop("subtasks", None)
            for k in ("description", "background", "input_format", "output_format",
                      "samples", "sample_groups", "constraints"):
                d.pop(k, None)
            d["can_edit"] = (role == "admin") or mine
            problems.append(d)

        cur = await db.execute("SELECT * FROM contests ORDER BY id")
        contests = []
        for r in await cur.fetchall():
            c = dict(r)
            if role != "admin" and c["id"] not in managed:
                continue
            c["phase"] = contest_phase(c)
            cur2 = await db.execute(
                "SELECT cp.slot, p.id, p.title, p.problem_type, p.score_total "
                "FROM contest_problems cp JOIN problems p ON p.id=cp.problem_id "
                "WHERE cp.contest_id=? ORDER BY cp.slot", (c["id"],))
            c["problems"] = [dict(x) for x in await cur2.fetchall()]
            cur3 = await db.execute(
                "SELECT u.id,u.username,u.display_name FROM contest_managers m "
                "JOIN users u ON u.id=m.user_id WHERE m.contest_id=?", (c["id"],))
            c["managers"] = [dict(x) for x in await cur3.fetchall()]
            c["can_edit"] = (role == "admin") or (c["id"] in managed)
            contests.append(c)

        users, teams = [], []
        if role == "admin":
            cur = await db.execute(
                "SELECT u.id,u.username,u.display_name,u.team_id,u.position,u.is_admin,t.name AS team_name "
                "FROM users u LEFT JOIN teams t ON t.id=u.team_id ORDER BY u.id")
            users = [dict(r) for r in await cur.fetchall()]
            cur = await db.execute("SELECT * FROM teams ORDER BY id")
            teams = [dict(r) for r in await cur.fetchall()]

        return {"problems": problems, "contests": contests, "users": users,
                "teams": teams, "difficulties": DIFFICULTIES,
                "role": role, "managed_contests": managed}
    finally:
        await db.close()


@app.get("/api/admin/problem/{pid}")
async def admin_get_problem(pid: int, user=Depends(current_user)):
    """Full problem record including subtasks and testcase file listing."""
    db = await get_db()
    try:
        await require_problem_owner(db, user, pid)
        p = await fetch_problem(db, pid)
        if not p: raise HTTPException(404)
        pdir = BASE / "data" / "problems" / (p["slug"] or f"p{pid}")
        files = []
        if pdir.exists():
            for f in sorted(pdir.iterdir()):
                if f.suffix in (".in", ".out"):
                    files.append({"name": f.name, "size": f.stat().st_size})
            ref = pdir / "ref.cpp"
            if not (p.get("std_source") or "").strip() and ref.exists():
                try:
                    p["std_source"] = ref.read_text(encoding="utf-8")
                except Exception:
                    pass
        p["files"] = files
        p["data_dir"] = str(pdir)
        return {"problem": p}
    finally:
        await db.close()


@app.post("/api/admin/problem")
async def admin_save_problem(
    id: Optional[int] = Form(None),
    slug: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    input_format: str = Form(""),
    output_format: str = Form(""),
    samples: str = Form(""),
    sample_groups: str = Form("[]"),
    background: str = Form(""),
    constraints: str = Form(""),
    time_limit: int = Form(1000),
    memory_limit: int = Form(256),
    problem_type: str = Form("standard"),
    score_total: int = Form(100),
    difficulty: str = Form(""),
    is_public: int = Form(0),
    tags: str = Form(""),
    position: Optional[int] = Form(None),
    interactive: int = Form(0),
    subtasks: str = Form("[]"),
    checker_type: str = Form("token"),
    spj_source: str = Form(""),
    std_source: str = Form(""),
    author: Optional[str] = Form(None),
    user=Depends(current_user),
):
    """Create or update a problem. Subtasks arrive as a JSON array."""
    slug = slug.strip()
    if not slug or "/" in slug or ".." in slug:
        raise HTTPException(400, "slug 非法")
    try:
        sts = json.loads(subtasks or "[]")
        assert isinstance(sts, list)
    except Exception:
        raise HTTPException(400, "子任务 JSON 格式错误")
    try:
        sgs = json.loads(sample_groups or "[]")
        assert isinstance(sgs, list)
    except Exception:
        raise HTTPException(400, "样例组 JSON 格式错误")

    db = await get_db()
    try:
        if id:
            # Editing: the author keeps rights over their own problem.
            await require_problem_owner(db, user, id)
        else:
            await require_problem_editor(db, user)
        cur = await db.execute("SELECT id FROM problems WHERE slug=? AND id IS NOT ?", (slug, id))
        clash = await cur.fetchone()
        if clash and clash["id"] != id:
            raise HTTPException(400, f"slug '{slug}' 已被题目 #{clash['id']} 占用")
        if problem_type != "mystery" and not (std_source or "").strip():
            raise HTTPException(400, "请填写标程 std（Hack 判定依赖标程，写入 ref.cpp）")

        # 出题人：管理员可任意指定；其他人只能署自己的名，且不得改动他人题目的署名
        if is_admin(user):
            author_name = (author or "").strip() or (user["display_name"] or user["username"])
        else:
            author_name = user["display_name"] or user["username"]
            if id:
                prev = await fetch_problem(db, id)
                if prev and (prev["author"] or "").strip():
                    author_name = prev["author"]     # preserve the original credit

        fields = dict(
            author=author_name,
            slug=slug, title=title, description=description, input_format=input_format,
            output_format=output_format, samples=samples,
            sample_groups=json.dumps(sgs, ensure_ascii=False),
            background=background, constraints=constraints,
            time_limit=time_limit, memory_limit=memory_limit, problem_type=problem_type,
            score_total=score_total, difficulty=difficulty, is_public=1 if is_public else 0,
            tags=tags, position=position, interactive=1 if interactive else 0,
            subtasks=json.dumps(sts, ensure_ascii=False),
            checker_type=checker_type if checker_type in ("token", "spj", "interactive") else "token",
        )
        # Persist the SPJ source next to the problem data so the judge can build it.
        pdir = BASE / "data" / "problems" / slug
        pdir.mkdir(parents=True, exist_ok=True)
        # Standard solution is required for Hack (ref.cpp). Always persist what we have.
        fields["std_source"] = std_source or ""
        (pdir / "ref.cpp").write_text(std_source or "", encoding="utf-8", newline="\n")
        if checker_type == "spj":
            (pdir / "spj.cpp").write_text(spj_source or "", encoding="utf-8", newline="\n")
            fields["spj_source"] = spj_source or ""
            fields["spj_compiled"] = 0        # needs a rebuild after every edit
        if id:
            sets = ",".join(f"{k}=?" for k in fields)
            await db.execute(f"UPDATE problems SET {sets} WHERE id=?", (*fields.values(), id))
            pid = id
        else:
            cols = ",".join(fields) + ",author_id,created_at"
            qs = ",".join("?" * (len(fields) + 2))
            cur = await db.execute(f"INSERT INTO problems({cols}) VALUES({qs})",
                                   (*fields.values(), user["id"], time.time()))
            pid = cur.lastrowid
        await db.commit()
        (BASE / "data" / "problems" / slug).mkdir(parents=True, exist_ok=True)
        return {"ok": True, "id": pid}
    finally:
        await db.close()


@app.delete("/api/admin/problem/{pid}")
async def admin_delete_problem(pid: int, user=Depends(current_user)):
    db = await get_db()
    try:
        await require_problem_owner(db, user, pid)
        cur = await db.execute("SELECT 1 FROM contest_problems WHERE problem_id=?", (pid,))
        if await cur.fetchone():
            raise HTTPException(400, "该题目已被比赛引用，请先从比赛中移除")
        await db.execute("DELETE FROM problems WHERE id=?", (pid,))
        await db.execute("DELETE FROM submissions WHERE problem_id=?", (pid,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@app.post("/api/admin/problem/{pid}/testdata")
async def admin_upload_testdata(pid: int, files: list[UploadFile] = File(...), user=Depends(current_user)):
    """Upload .in/.out testcase files into the problem's data directory."""
    db = await get_db()
    try:
        await require_problem_owner(db, user, pid)
        p = await fetch_problem(db, pid)
        if not p: raise HTTPException(404)
    finally:
        await db.close()
    pdir = BASE / "data" / "problems" / p["slug"]
    pdir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = os.path.basename(f.filename or "")
        if not name or "/" in name or ".." in name:
            continue
        if not name.endswith((".in", ".out", ".ans", ".cpp")):
            continue
        data = await f.read()
        # normalise line endings so Windows-authored data judges identically
        try:
            text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
            (pdir / name).write_text(text, encoding="utf-8", newline="\n")
        except UnicodeDecodeError:
            (pdir / name).write_bytes(data)
        saved.append(name)
    return {"ok": True, "saved": saved}


@app.post("/api/admin/problem/{pid}/autodetect")
async def admin_autodetect(pid: int, user=Depends(current_user)):
    """Scan the data dir and build subtasks from `{sub}_{case}.in` naming."""
    db = await get_db()
    try:
        await require_problem_owner(db, user, pid)
        p = await fetch_problem(db, pid)
        if not p: raise HTTPException(404)
        pdir = BASE / "data" / "problems" / p["slug"]
        if not pdir.exists():
            raise HTTPException(400, "题目数据目录不存在")
        groups = {}
        for f in sorted(pdir.glob("*.in")):
            stem = f.stem
            sub = 0
            if "_" in stem:
                head = stem.split("_")[0]
                if head.isdigit():
                    sub = int(head)
            out = pdir / (stem + ".out")
            groups.setdefault(sub, []).append(
                {"input": f.name, "output": out.name if out.exists() else ""})
        if not groups:
            raise HTTPException(400, "未找到任何 .in 文件")
        total = p["score_total"] or 100
        keys = sorted(groups)
        per = total // len(keys)
        sts = []
        for i, k in enumerate(keys):
            score = per if i < len(keys) - 1 else total - per * (len(keys) - 1)
            sts.append({"name": f"Subtask {k + 1}", "score": score, "testcases": groups[k]})
        await db.execute("UPDATE problems SET subtasks=? WHERE id=?",
                         (json.dumps(sts, ensure_ascii=False), pid))
        await db.commit()
        return {"ok": True, "subtasks": sts}
    finally:
        await db.close()


@app.get("/api/admin/spj_template")
async def admin_spj_template(user=Depends(current_user)):
    """A ready-to-edit testlib checker skeleton."""
    db = await get_db()
    try:
        await require_problem_editor(db, user)
    finally:
        await db.close()
    return {"template": SPJ_TEMPLATE, "testlib_available": (BASE / "data" / "lib" / "testlib.h").exists()}


@app.post("/api/admin/problem/{pid}/compile_spj")
async def admin_compile_spj(pid: int, user=Depends(current_user)):
    """Compile the problem's testlib special judge and report the g++ output."""
    db = await get_db()
    try:
        await require_problem_owner(db, user, pid)
        p = await fetch_problem(db, pid)
        if not p: raise HTTPException(404)
        pdir = BASE / "data" / "problems" / p["slug"]
        src = pdir / "spj.cpp"
        if not src.exists() or not (p.get("spj_source") or "").strip():
            raise HTTPException(400, "尚未填写 SPJ 源码")
        lib = BASE / "data" / "lib" / "testlib.h"
        if not lib.exists():
            raise HTTPException(400, "testlib.h 缺失（应位于 data/lib/testlib.h）")

        from judge import compile_spj, spj_binary_for
        out = spj_binary_for({"slug": p["slug"]})
        ok, log = await asyncio.to_thread(compile_spj, src, out)
        await db.execute("UPDATE problems SET spj_compiled=?, spj_log=? WHERE id=?",
                         (1 if ok else 0, log[-4000:], pid))
        await db.commit()
        if not ok:
            return JSONResponse({"ok": False, "log": log[-4000:]}, status_code=200)
        return {"ok": True, "log": log or "编译成功", "binary": str(out)}
    finally:
        await db.close()


@app.post("/api/admin/contest/{cid}/managers")
async def admin_set_managers(cid: int, user_ids: str = Form(""), user=Depends(current_user)):
    """Appoint contest managers. Admin-only: managers cannot appoint others."""
    require_admin(user)
    ids = [int(x) for x in user_ids.replace(" ", "").split(",") if x.strip().isdigit()]
    db = await get_db()
    try:
        await db.execute("DELETE FROM contest_managers WHERE contest_id=?", (cid,))
        for uid in ids:
            await db.execute(
                "INSERT OR IGNORE INTO contest_managers(contest_id,user_id,created_at) VALUES(?,?,?)",
                (cid, uid, time.time()))
        await db.commit()
        return {"ok": True, "managers": ids}
    finally:
        await db.close()


@app.post("/api/admin/problem/{pid}/delete_file")
async def admin_delete_file(pid: int, name: str = Form(...), user=Depends(current_user)):
    db = await get_db()
    try:
        await require_problem_owner(db, user, pid)
        p = await fetch_problem(db, pid)
        if not p: raise HTTPException(404)
    finally:
        await db.close()
    name = os.path.basename(name)
    f = BASE / "data" / "problems" / p["slug"] / name
    if f.exists() and f.suffix in (".in", ".out", ".ans"):
        f.unlink()
    return {"ok": True}


# ---------------- contests ----------------

@app.post("/api/admin/contest")
async def admin_save_contest(
    id: Optional[int] = Form(None),
    name: str = Form(...),
    label: str = Form(""),
    description: str = Form(""),
    start_time: str = Form(...),
    solve_duration: int = Form(7200),
    hack_duration: int = Form(3600),
    is_published: int = Form(1),
    user=Depends(current_user),
):
    """Create/update a contest. start_time accepts an epoch or 'YYYY-MM-DDTHH:MM'.

    Only admins may create contests or change scheduling; a contest manager can
    edit the description of a contest they own but never its team setup.
    """
    st = (start_time or "").strip()
    try:
        ts = float(st)
    except ValueError:
        import datetime
        try:
            ts = datetime.datetime.fromisoformat(st).timestamp()
        except Exception:
            raise HTTPException(400, "开始时间格式错误")
    db = await get_db()
    try:
        if id:
            await require_contest_editor(db, user, id)
        else:
            require_admin(user)          # only admins create contests
        if id:
            await db.execute(
                "UPDATE contests SET name=?,label=?,description=?,start_time=?,"
                "solve_duration=?,hack_duration=?,is_published=? WHERE id=?",
                (name, label, description, ts, solve_duration, hack_duration,
                 1 if is_published else 0, id))
            cid = id
        else:
            cur = await db.execute(
                "INSERT INTO contests(name,label,description,mode,start_time,solve_duration,"
                "hack_duration,is_published,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (name, label, description, "oil", ts, solve_duration, hack_duration,
                 1 if is_published else 0, time.time()))
            cid = cur.lastrowid
            if not label:
                await db.execute("UPDATE contests SET label=? WHERE id=?", (f"比赛 #{cid}", cid))
        await db.commit()
        return {"ok": True, "id": cid}
    finally:
        await db.close()


@app.post("/api/admin/contest/{cid}/problems")
async def admin_set_contest_problems(cid: int, mapping: str = Form(...), user=Depends(current_user)):
    """Replace a contest's problem set. `mapping` is JSON {slot: problem_id}."""
    try:
        m = json.loads(mapping)
        assert isinstance(m, dict)
    except Exception:
        raise HTTPException(400, "mapping 必须是 JSON 对象")
    db = await get_db()
    try:
        await require_contest_editor(db, user, cid)
        await db.execute("DELETE FROM contest_problems WHERE contest_id=?", (cid,))
        for slot, pid in m.items():
            if pid in (None, "", 0):
                continue
            await db.execute(
                "INSERT INTO contest_problems(contest_id,problem_id,slot) VALUES(?,?,?)",
                (cid, int(pid), slot))
        await db.commit()
        return {"ok": True, "count": len([v for v in m.values() if v])}
    finally:
        await db.close()


@app.delete("/api/admin/contest/{cid}")
async def admin_delete_contest(cid: int, user=Depends(current_user)):
    require_admin(user)
    db = await get_db()
    try:
        for t in ["contest_problems", "hacks", "personal_locks", "team_messages",
                  "submissions", "score_snapshots"]:
            await db.execute(f"DELETE FROM {t} WHERE contest_id=?", (cid,))
        await db.execute("DELETE FROM contests WHERE id=?", (cid,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# ---------------- users & teams ----------------

@app.post("/api/admin/user")
async def admin_save_user(
    id: int = Form(...),
    team_id: Optional[str] = Form(None),
    position: Optional[str] = Form(None),
    is_admin_flag: int = Form(0),
    display_name: Optional[str] = Form(None),
    user=Depends(current_user),
):
    """Assign a user to a team/position or toggle their admin flag."""
    require_admin(user)
    tid = int(team_id) if team_id not in (None, "", "null") else None
    pos = int(position) if position not in (None, "", "null") else None
    if pos is not None and not (0 <= pos <= 4):
        raise HTTPException(400, "位置必须是 0..4")
    db = await get_db()
    try:
        if tid is not None and pos is not None:
            cur = await db.execute(
                "SELECT id,display_name FROM users WHERE team_id=? AND position=? AND id<>?",
                (tid, pos, id))
            dup = await cur.fetchone()
            if dup:
                raise HTTPException(400, f"位置 {pos + 1} 已被 {dup['display_name']} 占用")
        if display_name:
            await db.execute("UPDATE users SET display_name=? WHERE id=?", (display_name, id))
        await db.execute("UPDATE users SET team_id=?, position=?, is_admin=? WHERE id=?",
                         (tid, pos, 1 if is_admin_flag else 0, id))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@app.post("/api/admin/team")
async def admin_save_team(
    id: Optional[int] = Form(None),
    name: str = Form(...),
    color: str = Form("#2f7ed8"),
    user=Depends(current_user),
):
    require_admin(user)
    db = await get_db()
    try:
        if id:
            await db.execute("UPDATE teams SET name=?, color=? WHERE id=?", (name, color, id))
            tid = id
        else:
            cur = await db.execute(
                "INSERT INTO teams(name,color,created_at) VALUES(?,?,?)",
                (name, color, time.time()))
            tid = cur.lastrowid
        await db.commit()
        return {"ok": True, "id": tid}
    finally:
        await db.close()


@app.post("/api/admin/rejudge/{sid}")
async def admin_rejudge(sid: int, user=Depends(current_user)):
    db = await get_db()
    try:
        await require_problem_editor(db, user)
        await db.execute("UPDATE submissions SET status='PENDING' WHERE id=?", (sid,))
        await db.commit()
    finally:
        await db.close()
    await JUDGE_QUEUE.put(sid)
    return {"ok": True}


@app.post("/api/admin/reset_contest/{cid}")
async def admin_reset(cid: int, user=Depends(current_user)):
    if not user or not user["is_admin"]:
        raise HTTPException(403)
    db = await get_db()
    try:
        now = time.time()
        await db.execute("UPDATE contests SET start_time=? WHERE id=?", (now, cid))
        for t in ["hacks","personal_locks","team_messages","submissions"]:
            await db.execute(f"DELETE FROM {t} WHERE contest_id=?", (cid,))
        await db.commit()
        return {"ok": True, "start_time": now}
    finally:
        await db.close()

@app.post("/api/admin/set_phase/{cid}")
async def admin_set_phase(cid: int, phase: str = Form(...), user=Depends(current_user)):
    """Admin: jump contest to a phase ('solve' or 'hack') by adjusting start_time."""
    if not user or not user["is_admin"]:
        raise HTTPException(403)
    db = await get_db()
    try:
        row = await db.execute("SELECT solve_duration, hack_duration FROM contests WHERE id=?", (cid,))
        c = await row.fetchone()
        if not c: raise HTTPException(404)
        now = time.time()
        if phase == "solve":
            await db.execute("UPDATE contests SET start_time=? WHERE id=?", (now, cid))
        elif phase == "hack":
            # jump to beginning of hack phase (solve just ended, full hack duration remaining)
            await db.execute("UPDATE contests SET start_time=? WHERE id=?",
                             (now - c["solve_duration"], cid))
        elif phase == "after":
            await db.execute("UPDATE contests SET start_time=? WHERE id=?",
                             (now - c["solve_duration"] - c["hack_duration"], cid))
        else:
            raise HTTPException(400, "unknown phase")
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

# ============================================================
# Judge workers
# ============================================================
def run_judge_sync(sid):
    """Synchronously judge a submission; runs in thread."""
    import sqlite3
    dbp = str(BASE / "data" / "oj.db")
    con = sqlite3.connect(dbp)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT s.*, p.* FROM submissions s JOIN problems p ON p.id=s.problem_id WHERE s.id=?", (sid,)).fetchone()
        if not row: return
        p = {k: row[k] for k in row.keys() if k in ("id","slug","time_limit","memory_limit","subtasks","validator","interactive","score_total","checker_type")}
        p["subtasks"] = json.loads(p["subtasks"] or "[]")

        # Mark as JUDGING and stream per-testcase progress into the DB so the
        # submission SSE endpoint can push live updates to the browser.
        con.execute("UPDATE submissions SET status='JUDGING' WHERE id=?", (sid,))
        con.commit()

        def on_progress(cases, partial):
            try:
                con.execute(
                    "UPDATE submissions SET case_results=?, score=? WHERE id=?",
                    (json.dumps(cases), partial, sid))
                con.commit()
            except Exception:
                pass

        result = judge_submission(p, row["code"], progress=on_progress)
        con.execute(
            "UPDATE submissions SET status=?, score=?, subtask_scores=?, case_results=?, verdict_detail=?, judged_at=? WHERE id=?",
            (result["status"], result["score"], json.dumps(result["subtask_scores"]),
             json.dumps(result["case_results"]), result.get("message",""), time.time(), sid))
        con.commit()
    finally:
        con.close()

def run_hack_sync(hid):
    import sqlite3
    dbp = str(BASE / "data" / "oj.db")
    con = sqlite3.connect(dbp)
    con.row_factory = sqlite3.Row

    def finish(status, message, detail=None):
        con.execute(
            "UPDATE hacks SET status=?, message=?, detail=?, judged_at=? WHERE id=?",
            (status, message, json.dumps(detail or {}, ensure_ascii=False), time.time(), hid))
        con.commit()

    try:
        h = con.execute("SELECT * FROM hacks WHERE id=?", (hid,)).fetchone()
        if not h: return
        con.execute("UPDATE hacks SET status='JUDGING' WHERE id=?", (hid,)); con.commit()

        p_row = con.execute("SELECT * FROM problems WHERE id=?", (h["problem_id"],)).fetchone()
        p = {k: p_row[k] for k in p_row.keys() if k in ("id","slug","time_limit","memory_limit","subtasks","validator","interactive","score_total","checker_type")}
        p["subtasks"] = json.loads(p["subtasks"] or "[]")

        # The attacker must be able to solve their own input: use their best
        # submission on this problem as the cross-check.
        atk_sub = con.execute(
            "SELECT * FROM submissions WHERE user_id=? AND problem_id=? AND contest_id=? "
            "ORDER BY score DESC, id DESC LIMIT 1",
            (h["attacker_id"], h["problem_id"], h["contest_id"])).fetchone()
        atk_code = atk_sub["code"] if atk_sub else None
        if atk_sub:
            con.execute("UPDATE hacks SET attacker_submission_id=? WHERE id=?", (atk_sub["id"], hid))
            con.commit()

        if h["kind"] == "personal":
            tgt_sub = con.execute(
                "SELECT * FROM submissions WHERE user_id=? AND problem_id=? AND contest_id=? "
                "ORDER BY score DESC, id DESC LIMIT 1",
                (h["target_id"], h["problem_id"], h["contest_id"])).fetchone()
            if not tgt_sub:
                return finish("INVALID", "对方没有提交")
            res = evaluate_hack(p, tgt_sub["code"], h["input_data"], attacker_code=atk_code)
            res["detail"]["target_submission_id"] = tgt_sub["id"]
            res["detail"]["attacker_submission_id"] = atk_sub["id"] if atk_sub else None
            return finish(res["verdict"], res["message"], res["detail"])

        # ---- team hack: every distinct correct solution must break ----
        solvers = con.execute(
            "SELECT s.id, s.user_id, s.code, u.display_name FROM submissions s "
            "JOIN users u ON u.id=s.user_id WHERE s.contest_id=? AND s.problem_id=? "
            "AND u.team_id=? AND s.score>=?",
            (h["contest_id"], h["problem_id"], h["target_team_id"], p_row["score_total"])).fetchall()
        if not solvers:
            return finish("INVALID", "对方没有正确做法")

        seen, targets = set(), []
        for row in solvers:
            if row["code"] in seen:
                continue
            seen.add(row["code"])
            targets.append(row)

        merged = {"stages": [], "runs": [], "per_member": [], "checker": ""}
        survivor = None
        for idx, row in enumerate(targets):
            res = evaluate_hack(p, row["code"], h["input_data"], attacker_code=None)
            d = res["detail"]
            if idx == 0:                       # std/attacker stages are shared
                merged["stages"] = d.get("stages", [])
                merged["checker"] = d.get("checker", "")
            if res["verdict"] == "INVALID":
                return finish("INVALID", res["message"], d)
            merged["per_member"].append({
                "user_id": row["user_id"], "display_name": row["display_name"],
                "submission_id": row["id"], "verdict": res["verdict"],
                "message": res["message"], "runs": d.get("runs", []),
            })
            if res["verdict"] != "SUCCESS":
                survivor = row
                break

        if survivor:
            return finish("FAILURE", f"{survivor['display_name']} 的做法通过了该测试", merged)
        return finish("SUCCESS", f"对方 {len(targets)} 份正确做法全部被击破", merged)
    except Exception as e:
        import traceback; traceback.print_exc()
        try:
            finish("SE", f"评测异常: {e}")
        except Exception:
            pass
    finally:
        con.close()

async def judge_worker(queue, fn):
    while True:
        item = await queue.get()
        try:
            await asyncio.to_thread(fn, item)
        except Exception as e:
            import traceback; traceback.print_exc()
        finally:
            queue.task_done()

def repair_exec_bits():
    """Restore the +x bit on helper binaries.

    Snapshots, zip archives and Windows checkouts all drop the execute bit, which
    used to make hack judging silently fall back to 'AC'. Cheap to redo on boot.
    """
    root = BASE / "data" / "problems"
    if not root.exists():
        return
    for pdir in root.iterdir():
        if not pdir.is_dir():
            continue
        for name in ("ref", "gen", "interactor", "spj"):
            for f in (pdir / name, pdir / (name + ".exe")):
                if f.exists() and not os.access(f, os.X_OK):
                    try:
                        f.chmod(0o755)
                    except Exception:
                        pass


@app.on_event("startup")
async def _startup():
    await init_db()
    repair_exec_bits()
    asyncio.create_task(judge_worker(JUDGE_QUEUE, run_judge_sync))
    asyncio.create_task(judge_worker(HACK_QUEUE, run_hack_sync))
    # Re-queue any pending submissions/hacks from before restart
    db = await get_db()
    try:
        for r in await (await db.execute("SELECT id FROM submissions WHERE status IN ('PENDING','JUDGING')")).fetchall():
            await JUDGE_QUEUE.put(r["id"])
        for r in await (await db.execute("SELECT id FROM hacks WHERE status='PENDING'")).fetchall():
            await HACK_QUEUE.put(r["id"])
    finally:
        await db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000,
                h11_max_incomplete_event_size=64*1024*1024,
                limit_concurrency=200)

# NOTE: two handlers used to live below this point — after uvicorn.run(), so they
# were never registered. They also called get_current_user()/db.get_problem(),
# neither of which exists here. Problem creation/editing goes through
# POST /api/admin/
