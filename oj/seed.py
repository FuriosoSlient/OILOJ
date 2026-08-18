"""Initialise a fresh OIL OJ database.

Creates the schema and a single administrator account. Nothing else — no demo
problems, no fake users, no generated test data.

This script is SAFE to re-run: it never drops tables and never deletes rows. If
an admin already exists it just reports and exits.

Usage:
    python seed.py                       # 建表 + 创建 admin / admin
    python seed.py myname mypassword     # 自定义管理员账号
    python seed.py --reset-admin NAME PW # 重置/提升某账号为管理员并改密码
"""
import asyncio
import sys
import time
from pathlib import Path

# Ensure UTF-8 console output on Windows (GBK default breaks Chinese logs)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from db import init_db, get_db, hash_password

DATA = Path(__file__).parent / "data" / "problems"


async def reset_admin(username, password):
    """Rescue path: make sure `username` exists, is an admin, and has this password."""
    await init_db()
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM users WHERE username=?", (username,))
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE users SET password_hash=?, is_admin=1 WHERE id=?",
                (hash_password(password), row["id"]))
            print(f"已重置账号 {username} 的密码，并赋予管理员权限。")
        else:
            await db.execute(
                "INSERT INTO users(username,password_hash,display_name,is_admin,created_at) "
                "VALUES(?,?,?,?,?)",
                (username, hash_password(password), username, 1, time.time()))
            print(f"账号 {username} 不存在，已新建为管理员。")
        # Old sessions keep working, but drop them so a stolen cookie can't linger.
        await db.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?)",
                         (username,))
        await db.commit()
        print(f"  登录：{username} / {password}")
    finally:
        await db.close()


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--reset-admin":
        if len(sys.argv) < 4:
            print("用法：python seed.py --reset-admin <用户名> <新密码>")
            return
        await reset_admin(sys.argv[2], sys.argv[3])
        return

    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    password = sys.argv[2] if len(sys.argv) > 2 else "admin"

    DATA.mkdir(parents=True, exist_ok=True)

    # Creates every table and applies pending column migrations.
    await init_db()
    print("数据库结构已就绪。")

    db = await get_db()
    try:
        cur = await db.execute("SELECT id, username FROM users WHERE is_admin=1 LIMIT 1")
        existing = await cur.fetchone()
        if existing:
            print(f"已存在管理员账号：{existing['username']}（未做任何修改）")
            return

        cur = await db.execute("SELECT id FROM users WHERE username=?", (username,))
        if await cur.fetchone():
            print(f"用户名 {username} 已被占用，请换一个：python seed.py <用户名> <密码>")
            return

        await db.execute(
            "INSERT INTO users(username,password_hash,display_name,is_admin,created_at) "
            "VALUES(?,?,?,?,?)",
            (username, hash_password(password), "Administrator", 1, time.time()))
        await db.commit()

        print("初始化完成。")
        print(f"  管理员：{username} / {password}")
        print("  请登录后在「管理后台」创建队伍、用户、题目与比赛。")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
