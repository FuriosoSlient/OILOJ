import sqlite3

con = sqlite3.connect("data/oj.db")
con.row_factory = sqlite3.Row

# 先看现在有谁
for r in con.execute("SELECT id, username, display_name FROM users ORDER BY id"):
    print(dict(r))

# 只改显示名（登录名不动）
con.execute(
    "UPDATE users SET display_name=? WHERE username=?",
    ("征酱白丝小脚踩爆我", "lker"),
)
con.execute(
    "UPDATE users SET display_name=? WHERE username=?",
    ("征酱白丝小脚踩爆我", "lk_er"),
)

# 登录名 + 显示名一起改
# con.execute(
#     "UPDATE users SET username=?, display_name=? WHERE id=?",
#     ("new_login", "新名字", 14),
# )

con.commit()
con.close()