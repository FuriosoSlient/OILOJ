"""Async SQLite database layer for the OJ."""
import aiosqlite, json, time, os, hashlib, secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "oj.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    team_id INTEGER,
    position INTEGER,
    is_admin INTEGER DEFAULT 0,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    color TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    background TEXT DEFAULT '',          -- optional flavour text, hidden when empty
    input_format TEXT,
    output_format TEXT,
    samples TEXT,
    sample_groups TEXT DEFAULT '[]',     -- JSON [{input, output, note}]
    constraints TEXT,
    time_limit INTEGER DEFAULT 1000,
    memory_limit INTEGER DEFAULT 256,
    problem_type TEXT DEFAULT 'standard', -- standard | personal | thinking | mystery
    score_total INTEGER DEFAULT 100,
    subtasks TEXT, -- JSON list of {name, score, testcases:[...]}
    validator TEXT, -- optional custom checker source path
    position INTEGER, -- for personal problems: 0..4
    interactive INTEGER DEFAULT 0,
    difficulty TEXT DEFAULT '',          -- 入门/普及-/普及/普及+/提高/提高+/省选/NOI-/NOI/NOI+
    is_public INTEGER DEFAULT 0,         -- 1 = publicly listed outside contests
    tags TEXT DEFAULT '',                -- comma separated
    checker_type TEXT DEFAULT 'token',   -- token | spj | interactive
    spj_source TEXT DEFAULT '',          -- testlib-based C++ checker source
    spj_compiled INTEGER DEFAULT 0,      -- 1 = binary built and up to date
    spj_log TEXT DEFAULT '',             -- last compile output
    created_at REAL
);

CREATE TABLE IF NOT EXISTS contests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    mode TEXT DEFAULT 'oil',
    start_time REAL,
    solve_duration INTEGER DEFAULT 7200,
    hack_duration INTEGER DEFAULT 3600,
    label TEXT DEFAULT '',               -- e.g. "比赛 #1"
    description TEXT DEFAULT '',
    is_published INTEGER DEFAULT 1,      -- visible in contest list before start
    created_at REAL
);

-- Users who may prepare problems/data for a contest without touching team setup
CREATE TABLE IF NOT EXISTS contest_managers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER,
    user_id INTEGER,
    created_at REAL,
    UNIQUE(contest_id, user_id)
);

-- Periodic snapshots of team/user scores for the live standings chart
CREATE TABLE IF NOT EXISTS score_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER,
    ts REAL,
    payload TEXT   -- JSON {teams:{tid:score}, users:{uid:score}}
);
CREATE INDEX IF NOT EXISTS idx_snap_contest ON score_snapshots(contest_id, ts);

CREATE TABLE IF NOT EXISTS contest_problems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER,
    problem_id INTEGER,
    slot TEXT, -- 'personal:0' .. 'personal:4' or 'team:0'.. or 'mystery'
    UNIQUE(contest_id, slot)
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    problem_id INTEGER,
    contest_id INTEGER,
    code TEXT,
    language TEXT DEFAULT 'C++20',
    status TEXT DEFAULT 'PENDING',
    score INTEGER DEFAULT 0,
    subtask_scores TEXT, -- JSON list per subtask
    case_results TEXT, -- JSON detailed results
    verdict_detail TEXT,
    created_at REAL,
    judged_at REAL
);

CREATE TABLE IF NOT EXISTS hacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER,
    attacker_id INTEGER,
    target_id INTEGER,
    target_team_id INTEGER,
    problem_id INTEGER,
    submission_id INTEGER,
    kind TEXT, -- 'personal' | 'team'
    subtask_indices TEXT, -- JSON list for personal
    input_data TEXT,
    status TEXT DEFAULT 'PENDING', -- PENDING | SUCCESS | FAILURE | INVALID
    message TEXT,
    detail TEXT DEFAULT '',        -- JSON: per-stage std/attacker/victim run info
    attacker_submission_id INTEGER,-- attacker's own solution used for validation
    created_at REAL,
    judged_at REAL,
    UNIQUE(contest_id, attacker_id, problem_id, target_id, subtask_indices, input_data)
);

CREATE TABLE IF NOT EXISTS personal_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER,
    user_id INTEGER,
    locked_at REAL,
    UNIQUE(contest_id, user_id)
);

CREATE TABLE IF NOT EXISTS team_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER,
    team_id INTEGER,
    user_id INTEGER,
    message TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER,
    created_at REAL,
    expires_at REAL
);

-- Per-contest teams (OIL / ICPC). Global `teams` is kept for display leftovers.
CREATE TABLE IF NOT EXISTS contest_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contest_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS contest_members (
    contest_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    team_id INTEGER,
    position INTEGER,
    PRIMARY KEY (contest_id, user_id)
);

CREATE TABLE IF NOT EXISTS rating_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    contest_id INTEGER,
    old_rating INTEGER,
    new_rating INTEGER,
    rank INTEGER,
    score REAL,
    created_at REAL
);
"""

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    return db

# Columns added after the initial release. Applied with ALTER TABLE on existing DBs
# so upgrading never loses data.
MIGRATIONS = [
    ("problems", "difficulty",   "TEXT DEFAULT ''"),
    ("problems", "is_public",    "INTEGER DEFAULT 0"),
    ("problems", "tags",         "TEXT DEFAULT ''"),
    ("problems", "checker_type", "TEXT DEFAULT 'token'"),
    ("contests", "label",        "TEXT DEFAULT ''"),
    ("contests", "description",  "TEXT DEFAULT ''"),
    ("contests", "is_published", "INTEGER DEFAULT 1"),
    ("problems", "spj_source",   "TEXT DEFAULT ''"),
    ("problems", "spj_compiled", "INTEGER DEFAULT 0"),
    ("problems", "spj_log",      "TEXT DEFAULT ''"),
    ("problems", "background",    "TEXT DEFAULT ''"),
    ("problems", "sample_groups", "TEXT DEFAULT '[]'"),
    ("problems", "author",        "TEXT DEFAULT ''"),
    ("problems", "author_id",     "INTEGER DEFAULT 0"),
    ("hacks",    "detail",       "TEXT DEFAULT ''"),
    ("hacks",    "attacker_submission_id", "INTEGER"),
    ("problems", "std_source",   "TEXT DEFAULT ''"),
    ("submissions", "locked_submit", "INTEGER DEFAULT 1"),
    ("users", "rating", "INTEGER DEFAULT 1500"),
    ("contests", "is_rated", "INTEGER DEFAULT 0"),
    ("contests", "rating_applied", "INTEGER DEFAULT 0"),
    ("problems", "file_io_in", "TEXT DEFAULT ''"),
    ("problems", "file_io_out", "TEXT DEFAULT ''"),
    ("problems", "use_subtasks", "INTEGER DEFAULT 1"),
    ("problems", "hack_validator", "TEXT DEFAULT ''"),
]


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await get_db()
    try:
        for stmt in SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                await db.execute(s)
        # Non-destructive migrations for databases created by older versions
        for table, col, decl in MIGRATIONS:
            cur = await db.execute(f"PRAGMA table_info({table})")
            cols = {r[1] for r in await cur.fetchall()}
            if col not in cols:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        await db.execute(
            "CREATE TABLE IF NOT EXISTS contest_virtuals ("
            "contest_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
            "started_at REAL NOT NULL, PRIMARY KEY (contest_id, user_id))")
        await db.commit()
    finally:
        await db.close()

def hash_password(pw: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.sha256((salt + pw).encode()).hexdigest()
    return f"{salt}${h}"

def verify_password(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
        return hashlib.sha256((salt + pw).encode()).hexdigest() == h
    except Exception:
        return False

async def create_session(db, user_id: int) -> str:
    token = secrets.token_hex(24)
    now = time.time()
    await db.execute(
        "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES(?,?,?,?)",
        (token, user_id, now, now + 7*86400),
    )
    await db.commit()
    return token

async def user_from_token(db, token: str):
    if not token:
        return None
    row = await db.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?",
        (token, time.time()),
    )
    return await row.fetchone()

# NOTE: get_problems() / create_problem() / update_problem() were removed.
# They targeted a different schema (a `hint` column, no `slug`/`subtasks`) and were
# never reachable: this app reads problems through fetch_problem() in main.py and
# writes them through the /api/admin/problem endpoint.
