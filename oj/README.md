# OIL OJ — 仿 LOJ 的在线评测 & OIL 赛制系统

一个本地运行的在线评测平台，UI 仿照 [LOJ](https://loj.ac)，提交仅允许 **GNU C++20**，在本地沙箱编译运行后返回结果。
内置一种特殊赛制 **OIL**（两支 5 人队伍对抗，个人题 + 团队思维题 + 神秘交互题，含做题阶段与公开 Hack 阶段）。

## 启动

```bash
cd /home/user/oj
pip install fastapi uvicorn aiosqlite python-multipart   # 已安装可跳过
python3 main.py
```

浏览器打开 http://localhost:8000

首次运行需初始化题库与测试数据（已执行过一次；如需重建）：

```bash
cd /home/user/oj
rm -rf data/oj.db data/problems/*/
python3 seed.py
```

## 测试账号

| 账号 | 密码 | 队伍 | 位置 |
|------|------|------|------|
| `alice1` ~ `alice5` | `123456` | Code Rangers (A) | 1~5 |
| `bob1` ~ `bob5` | `123456` | Bit Warriors (B) | 1~5 |
| `admin` | `admin` | 管理员 | — |

> 用两个浏览器/无痕窗口分别登录两队账号，可同时体验对抗与信息隔离。

## 赛制规则（OIL）

- **队伍配置**：两队各 5 人。
- **题目组成**：
  - 每人 1 道**个人题**（绿题难度，多子任务，部分分齐全）。
  - 4 道**思维题**（蓝题难度，每题 50 分，无部分分，可被 Hack）。
  - 1 道**神秘题**（人类智慧 / 交互题，200 分，禁止 Hack）。
- **时间**：2 小时做题阶段 + 1 小时公开 Hack 阶段。

### 信息隔离与锁题
- 开赛时每人只能看到**自己的个人题**，团队题不可见，队内不可交流。
- **锁定个人题**后：
  - 无法再修改个人题的任何提交；
  - 可与同样锁题的队友交流；
  - 解锁团队题查看/提交权限；
  - 获得 Hack 对方同位置选手个人题的资格。
- 未锁题成员只能看到其他人是否已锁题。

### 个人题 Hack（做题阶段，逐子任务攻击）
- 每个子任务是独立攻击目标，可任选一个或多个发起 Hack。
- 某子任务被 Hack 成功，对方该子任务得分变为原来的 **40%**（损失 60%），攻击方不得分。
- 例：10+20+30 中 30 分子任务被 Hack → 10+20+12 = 42。

### 团队题 Hack（公开 Hack 阶段，仅思维题）
- 必须 Hack 掉对方某题**所有正确做法**才算成功。
- 成功后对方该题得分变为 **30%**，攻击方获得该题满分的 **70%**（真正的"窃取"）。
- 神秘题禁止 Hack。

## 功能页面

- `/` 首页与赛制说明
- `/problems` 题库
- `/problem/{id}` 题面、提交、子任务得分
- `/status` 全局评测状态（自动刷新）
- `/contest/1` OIL 比赛主控台：记分板、题目、锁题、队伍讨论（SSE 实时推送）、Hack 中心
- 管理员可在比赛页右上角**重置比赛 / 切换阶段**（做题→公开 Hack→结束），便于测试。

## 架构

- 后端：FastAPI + aiosqlite（`main.py` 路由，`db.py` 数据层，`judge.py` 本地评测）。
- 评测：`g++ -std=c++20 -O2 -w` 编译，子进程限时运行，支持 token 比对、自定义 checker 与交互题 interactor。
- 前端：服务端渲染静态 HTML + 原生 JS（`static/app.js`），仿 LOJ 深色侧边栏风格；比赛状态通过 SSE（`/api/contest/{id}/stream`）3 秒推送一次。
- 后台：两个 asyncio worker 分别消费提交队列与 Hack 队列（`asyncio.to_thread` 同步评测，不阻塞事件循环）。

## 题目与数据

题库由 `seed.py` 生成，含 10 题：

| Slug | 题目标题 | 类型 | 分值 |
|------|----------|------|------|
| p-sum | 区间求和 | 个人题 1 | 100（5 子任务） |
| p-lis | 最长上升子序列计数 | 个人题 2 | 100（5 子任务） |
| p-graph | 最短路计数 | 个人题 3 | 100（5 子任务） |
| p-knapsack | 分组背包 | 个人题 4 | 100（5 子任务） |
| p-string | 子串统计 | 个人题 5 | 100（5 子任务） |
| t-xor | 异或配对 | 思维题 | 50 |
| t-game | 取石子游戏 | 思维题 | 50 |
| t-matrix | 矩阵构造 | 思维题 | 50 |
| t-perm | 置换还原 | 思维题 | 50 |
| x-mystery | 【神秘】隐藏的数 | 交互题 | 200 |

每题的测试数据由 `gen.cpp` 生成、参考输出由 `ref.cpp` 产生，存于 `data/problems/<slug>/`。
要新增题目：在 `seed.py` 的 `PROBLEMS` 中追加定义（题面、子任务、`gen.cpp`、`ref.cpp`），重新运行 `python3 seed.py` 即可。

## 已验证的行为

- 正确代码 → AC 与各子任务满分；错误代码 → WA/TLE/RE/CE 及部分分。
- 交互题二进制二分查找 → 200 分。
- 个人题 Hack 成功：10/20/30 三个子任务被攻破后分别变为 4/8/12。
- 团队题 Hack 成功：对方 50→15，攻击方 +35（70% 窃取），队伍总分实时更新。
- 锁题后无法再提交个人题；未锁题看不到团队题与队内聊天；只有同位置可 Hack 个人题；公开 Hack 阶段只能 Hack 思维题。

---

## Windows 运行说明（跨平台兼容修复）

原先代码只在 Linux 下测试过，在 Windows 上会有三类问题，现已全部修复：

### 1. `UnicodeDecodeError: 'gbk' codec can't decode byte 0x80`
Windows 上 Python 的 `open()` / `Path.read_text()` 默认使用 **GBK** 编码，
而项目里的模板、题面、测试数据都是 UTF-8，于是读文件直接崩溃。

修复：
- `main.py` 的 `Render()`：`tpath.read_text(encoding="utf-8")`
- `judge.py`：新增 `read_text()` / `write_text()` 辅助函数，全部强制
  `encoding="utf-8", errors="replace"`，写入时 `newline="\n"`（避免 Windows 把
  `\n` 变成 `\r\n` 导致测试数据与答案不一致）
- `seed.py`：新增 `wtext()`，所有 `.cpp` / `.in` / `.out` 写入均为 UTF-8 + LF
- 所有 `subprocess.run(...)` 增加 `encoding="utf-8", errors="replace"`
  （否则 g++ 的中文/UTF-8 报错信息在 Windows 上会再次触发 GBK 解码错误）
- `main.py` / `seed.py` 启动时 `sys.stdout.reconfigure(encoding="utf-8")`，
  保证中文日志不会在 GBK 控制台上报错

### 2. POSIX 专用 API（`os.setsid` / `os.killpg` / `SIGKILL`）
这些在 Windows 上不存在，评测进程一旦 TLE 就会崩。

修复：`judge.py` 增加跨平台封装
- `_popen_kwargs()`：Linux/macOS 用 `start_new_session=True`，
  Windows 用 `creationflags=CREATE_NEW_PROCESS_GROUP`
- `kill_tree(proc)`：Linux/macOS 用 `os.killpg(..., SIGKILL)`，
  Windows 用 `taskkill /F /T /PID`，失败再退回 `proc.kill()`

### 3. 可执行文件缺 `.exe` 后缀
`g++ -o ref` 在 Windows 上生成的是 `ref.exe`，原代码按 `ref` 去找会全部 "文件不存在"。

修复：`judge.py` / `seed.py` 引入 `EXE = ".exe" if os.name == "nt" else ""`
和 `exe_path()`，编译产物（sol / checker / gen / ref / interactor）统一带后缀。
数据库中存的 interactor 路径也会带上 `.exe`。

> ⚠️ 换平台后请重新 seed 一次，让二进制与路径匹配：
> ```
> rm -rf data/oj.db data/problems/*/      # Windows: rmdir /s /q ...
> python seed.py
> ```

### 顺带修掉的三个真实 Bug
1. **表单 1MB 限制**：新版 Starlette 的 `max_part_size` 是构造函数关键字默认值，
   改类属性无效。现在直接 patch `MultiPartParser.__init__` / `FormParser.__init__`，
   上限提到 64MB；Hack 输入上限从 2MB 提到 16MB（大数据卡常 Hack 必需）。
2. **`/api/hack` 的 `subtask_indices`**：只接受 JSON 数组，传 `"0,1,2"` 会 500。
   现在两种格式都接受。
3. **评测结果永远显示 AC**：`run_judge_sync` 组装题目字典时漏了 `score_total`，
   导致 `judge.py` 里 `total >= full`（full=0）恒成立，60 分的暴力也被标成 AC。
   现已补上，暴力解正确显示 `TLE / 60 分`。

### Windows 前置条件
- 安装 MinGW-w64 / MSYS2，确保 `g++ --version` 可用且支持 `-std=c++20`
- 建议控制台执行 `chcp 65001` 切到 UTF-8 代码页

---

# v2 新增功能

## 1. Markdown + LaTeX 题面

题面全面改用 **Markdown + LaTeX** 渲染，支持标题、列表、表格、代码块、引用、加粗等。

公式语法：

| 类型 | 写法 |
|---|---|
| 行内 | `$O(n\log n)$` 或 `\(...\)` |
| 行间 | `$$\sum_{i=1}^{n} a_i^2$$` 或 `\[...\]` |

实现要点（`static/app.js` 的 `renderStatement()`）：
1. **先**把代码块 / 行内代码抽出占位，避免公式解析误伤代码；
2. **再**抽出数学公式占位 —— 必须在 Markdown 之前，否则 marked 会把
   `\sum`、`_i` 当成转义或斜体，公式会碎掉；
3. 跑 marked 解析 Markdown；
4. 用 KaTeX 把占位符换回渲染好的公式；
5. 最后用 DOMPurify 消毒（题面是管理员手写 HTML，防 XSS）。

> **全部依赖已本地化**到 `static/vendor/`（KaTeX + marked + DOMPurify，约 1MB），
> **完全离线可用**，不依赖任何 CDN。

## 2. 网页端配置题目与数据（仅管理员）

新增 `/admin` 管理后台，四个分页：

- **题目管理** —— 新建/编辑/删除题目，Markdown 题面**左写右实时预览**，
  可视化编辑子任务与分值、测试点映射
- **比赛管理** —— 新建/编辑比赛，配置 11 个题位（5 个人题 + 5 思维题 + 1 神秘题）
- **用户与队伍** —— 建队伍、分配队伍/位置、授予管理员
- **测试数据** —— 上传 `.in/.out`，一键**自动识别子任务**

所有 `/api/admin/*` 接口都经 `require_admin()` 校验，非管理员一律 403（已测）。
上传的数据会自动把 CRLF 归一为 LF，避免 Windows 编辑的数据判错。

**自动识别**按 `{子任务号}_{测试点号}.in/.out` 命名约定分组，例如
`0_0.in`、`0_1.in` → 子任务 1；`1_0.in` → 子任务 2，分值自动均分。

## 3. 比赛封装与题目可见性

比赛现在有独立编号（`比赛 #1`、`比赛 #2`）、开始时间、说明、发布状态。
新增 `/contests` 比赛列表页，按「进行中 / 即将开始 / 已结束」分组。

可见性规则统一收敛到 `problem_visibility()` 一个函数（原来散落在 4 处）：

| 时机 | 题目可见性 | 难度 | Hack 数据 |
|---|---|---|---|
| 比赛开始前 | **完全不可见**（含标题） | 隐藏 | 否 |
| 比赛期间 | 按 OIL 锁题规则部分可见 | **隐藏（显示 ???）** | 否 |
| 比赛结束后 | **自动公开** | **公布** | **公布** |
| 标记 public 且不属于未结束比赛 | 公开 | 公布 | 否 |

注意一个防泄题细节：即使题目被标记为 public，只要它还属于某个**未结束**的比赛，
仍然会被隐藏 —— 否则选手能提前从题库预览赛题。

## 4. 评测结果实时同步

- `judge.py` 的 `judge_submission()` 新增 `progress` 回调，**每跑完一个测试点**
  就回写数据库
- 新增 SSE 接口 `GET /api/submission/{sid}/stream`，变化即推送
- 前端 `followSubmission()` 用 `EventSource` 订阅，断线自动退回轮询
- 提交页实时显示**测试点色块矩阵**和当前得分

实测一次提交的推送序列：`JUDGING 0 个测试点 (0分) → 11 个 (80分) → AC 13 个 (100分)`。

## 5. 管理员入口

侧边栏管理员登录后会出现「**⚙️ 管理后台**」入口（普通用户不显示），
用户名旁也会显示「管理员」标记。比赛列表页右上角另有一个快捷入口。

## 6. 实时榜单与分数折线图

新增 `/contest/{id}/standings`：

- 队伍总分实时排名（每 5 秒刷新）
- **分数变化折线图**，可切换「按队伍 / 按选手」视角
- 明细表：每位选手个人题得分、Hack 窃取得分、各团队题得分

折线图是**手写 SVG 阶梯折线**（分数是离散跳变的，阶梯图比平滑曲线更准确），
无任何图表库依赖，同样离线可用。数据来自新增的 `score_snapshots` 表，
在比赛 SSE 流里采样（有变化即记录，否则最多 60 秒一个点）。

## 数据库迁移

`db.py` 新增 `MIGRATIONS` 列表，用 `ALTER TABLE ADD COLUMN` 增量升级，
**老数据库直接启动即可自动迁移，不会丢数据**：

- `problems`：`difficulty`、`is_public`、`tags`、`checker_type`
- `contests`：`label`、`description`、`is_published`
- 新表：`score_snapshots`

## 本次顺带修复的 Bug

- `/api/admin/set_phase` 的 `after` 分支：SQL 只 SELECT 了 `solve_duration`
  却访问 `hack_duration`，导致 500（`IndexError: No item with that key`）
- 重启后处于 `JUDGING` 中断状态的提交现在也会重新入队（原来只捞 `PENDING`）

---

# v3 修复与新增

## 1. 比赛负责人（出题人）

管理员可为**每场比赛**指定负责人（管理后台 → 比赛管理 → 编辑 → 比赛负责人）。

| 能力 | 管理员 | 比赛负责人 | 普通选手 |
|---|:--:|:--:|:--:|
| 进入管理后台 | ✅ | ✅ | ❌ |
| 创建/编辑题目、上传数据、配置 SPJ | ✅ | ✅ | ❌ |
| 编辑**自己负责**的比赛题目配置 | ✅ | ✅ | ❌ |
| 编辑他人负责的比赛 | ✅ | ❌ | ❌ |
| 新建/删除比赛 | ✅ | ❌ | ❌ |
| **分队 / 用户权限 / 任命负责人** | ✅ | **❌** | ❌ |

负责人登录后，后台的「用户与队伍」分页**根本不会出现**，
后端 `/api/admin/user`、`/api/admin/team`、`/api/admin/contest/{id}/managers`
也一律返回 403 —— 界面与接口双重拦截。

新增表 `contest_managers`，权限判定集中在
`require_problem_editor()` / `require_contest_editor()`。

## 2. 管理入口与后台 UI

- 侧边栏新增「⚙️ 管理后台」（管理员/负责人可见）
- 每个页面右下角有**悬浮按钮**，进后台不用找
- 用户名旁显示「管理员」/「出题负责人」标记
- 后台新增**顶部信息卡**（题目数、比赛数、进行中、SPJ 题数）
- 负责人会看到一条橙色提示，说明自己的权限边界

## 3. 修复：题目列表在比赛期间为空

`/api/problems` 原先不带比赛上下文，导致比赛进行中选手打开题库看到**空列表**
（自己的个人题也看不到）。

现在 `problem_visibility()` 在没有显式 `contest_id` 时，会自动回退到
「该题所属的进行中比赛」的 OIL 规则。效果：选手在题库里能看到自己的个人题，
锁题后还能看到团队题，且**难度显示为 `???`**。

另外题目详情页不再直接返回 403 JSON，而是渲染页面骨架并给出友好提示
（侧边栏保留），真正的权限校验仍在 API 层。

## 4. 比赛列表

首页「进入 OIL 比赛」的硬编码链接已改为 `/contests` 比赛列表；
比赛详情页顶部新增**比赛切换下拉框**和「全部比赛」按钮。
所有人都能看到比赛列表并自行选择进入。

## 5. SPJ 特殊评测（testlib）

- `data/lib/testlib.h` 已内置（官方版本，6252 行）
- 后台题目编辑页新增「评测方式」下拉：`逐 token 比对` / `SPJ 特殊评测`
- 选择 SPJ 后出现代码编辑区，可「载入模板」「编译 SPJ」，
  **编译日志直接显示在页面上**
- 编译时自动附加 `-I data/lib`，无需手动管理头文件
- 完全支持 testlib 的退出码约定：`_ok`→AC、`_wa`/`_pe`→WA、`_fail`→SE

实测：一道「两数之和，输出任意一组解」的题目，
标准答案文件写 `1 2`，选手输出 `2 1`（另一组合法解）→ **AC**；
输出 `1 1`（i==j）或 `1 3`（和不对）→ **WA**。

## 6. 去掉 UI 中的测试信息

首页的「测试账号」表格（alice/bob/admin 及密码）已删除，
比赛页的「请使用测试账号 alice1~alice5 登录」提示改为
「请联系管理员将你加入参赛队伍」。

## 本轮顺带修复的两个严重 Bug

**(1) `fetch_contest` 的 SQL 列名冲突** —— `SELECT cp.*, p.*` 中两张表都有 `id`，
`contest_problems.id` 覆盖了 `problems.id`，导致比赛题目的 id 全错，
提交时报「该题不在比赛中」。原先 seed 出来的数据恰好 `cp.id == problem_id`
所以一直没暴露，一旦在后台重新配置题目就必现。
已改为 `SELECT cp.slot AS slot, p.*`。

**(2) 评测二进制丢失可执行权限导致 Hack 静默判 AC** ——
快照/压缩包/Windows 检出都会丢掉 `+x`，此时 `pdir/ref` 无法执行，
而旧代码在「拿不到标程输出」时会 **默认判 AC**，Hack 全部误判为失败。
现在：
- 启动时自动修复所有 `ref/gen/interactor/spj` 的可执行位
- 二进制缺失会尝试用 `ref.cpp` 重新编译
- **拿不到标程输出时返回 SE 并说明原因，绝不静默判 AC**

---

# v3.1 缓存问题修复

## 根因：浏览器缓存了旧的 app.js / style.css

上一版报告的三个问题其实是**同一个原因**——服务器上的文件已经更新，
但浏览器仍在使用缓存的旧版静态资源：

| 现象 | 实际原因 |
|---|---|
| `difficultyBadge is not defined` | 旧 `app.js` 里没有这个函数 |
| 看不到 admin 入口 | 旧 `app.js` 里没有 `renderAdminFab`，侧栏还是旧的硬编码「OIL 比赛」 |
| 比赛列表 card 渲染崩了 | 旧 `style.css` 里没有 `.contest-card` / `.phase-chip` 等样式 |

侧栏链接指向单场比赛而不是列表，也是同一个旧文件造成的。

## 修复：自动版本戳（cache-busting）

`Render()` 现在会给**第一方**静态资源加上基于文件修改时间的版本号：

```html
<link rel="stylesheet" href="/static/style.css?v=1786974871">
<script src="/static/app.js?v=1786974871"></script>
```

同时 HTML 外壳返回 `Cache-Control: no-cache, no-store, must-revalidate`
（否则外壳本身被缓存，会一直指向旧的 `?v=`，机制就失效了）。

文件一改，`?v=` 自动变化，浏览器立即拉取新版本 —— **以后升级不需要再手动强刷**。

> 说明：`/static/vendor/` 下的 KaTeX、marked、DOMPurify 是固定版本的第三方库，
> 不加版本号，继续走长缓存，省流量。

## 顺带修复：榜单队伍行重复 class 属性

`standings.html` 里写成了：

```html
<div class="flex-between" style="..." class="rank-1">   <!-- 错误 -->
```

HTML 中重复的 `class` 属性，**第二个会被浏览器直接忽略**，所以 `rank-1`/`rank-2`
的高亮样式从未生效。已合并为 `class="flex-between rank-1"`。

## 验证结果（真实 DOM 环境）

- 管理后台点击「题目管理」：**无 JS 错误**，14 行题目、4 个难度徽章正常渲染
- 侧边栏：首页 / 题目 / **比赛→/contests** / 评测状态 / ⚙️ 管理后台
- 悬浮按钮：管理员 ✅、负责人 ✅、选手 ❌、匿名 ❌
- 比赛列表：2 张卡片，阶段标签「🔒 做题阶段」「未开始」，标题正常
- 榜单：队伍行 class 正确为 `flex-between rank-1` / `flex-between rank-2`

---

# v4 Hack 流程重构 & 提交可见性

## 1. Hack 三阶段判定

以前 Hack 只是「把对方代码跑一遍」，现在按你要求改成三阶段：

```
① 标程 (std)      跑一次 → 失败则判 INVALID（数据非法，不罚任何人）
② 攻击方程序        跑一次 → 失败则判 INVALID（你自己都做不对，Hack 无效）
③ 被 Hack 的程序    跑 5 次 → 任意一次失败即 Hack 成功
```

跑 5 次是为了抓**非确定性代码**：未初始化内存、依赖 `rand()`、哈希随机化、
多线程竞争、不稳定排序等，单次运行可能侥幸通过。

- 标程运行时**不设内存上限**、时限放宽到 5 倍：它只负责给出正确答案，
  用的内存本来就可能比选手限制多（实测标程读 1.3MB 输入要 90MB）。
- 团队 Hack 对**每一份**去重后的正确做法各跑 5 次，全部击破才算成功。

## 2. Hack 结果与详情

Web 端提交 Hack 后不再「没有反馈」：

- 通过 SSE (`/api/hack/{id}/stream`) **实时推送判定结果**
- 判定完成后自动展开**完整报告**：

| 阶段 | 结果 | 用时 | 内存 | 判定 |
|---|---|---|---|---|
| 标准程序 (std) | AC | 25 ms | 88.1 MB | |
| 攻击方程序 | AC | 25 ms | 88.1 MB | 输出一致 |
| 被 Hack 程序 第 1/5 次 | TLE | 1000 ms | — | 未产生有效输出 |

还会显示判定方式（SPJ / 逐 token 比对）、各程序输出、以及团队 Hack 时
每位成员做法的击破情况。

### 内存统计终于是真的了

原来 `max_rss_kb` 恒为 0。现在用 `os.wait4()` 读取**该进程自己**的 peak RSS。

> 踩坑记录：一开始用 `resource.getrusage(RUSAGE_CHILDREN)`，它是**所有子进程
> 的粘性最高水位**，跑完一个大内存程序后，之后每个小程序都会报同样的高内存，
> 直接导致标程被误判 MLE、Hack 全部变成 INVALID。必须用 `wait4` 按进程取。

MLE 现在也能真正判定了（实测 150MB 程序在 64MB 限制下正确判 MLE）。

## 3. Hack 进入评测大表

`/status` 页面现在是**提交 + Hack 的统一时间线**，可按类型筛选：

```
H21  个人 Hack  A1 → B1   区间求和   Hack 成功
#59  提交       A1        区间求和   Accepted 100
```

点 `H21` 展开完整 Hack 报告，点 `#59` 展开提交详情。

## 4. BUG2：比赛期间的提交可见性

新增 `submission_access()` 统一判定，规则完全按你的要求：

| 观看者 | 列表可见 | 详情（代码/测试点） |
|---|:--:|:--:|
| 本人 / 管理员 | ✅ | ✅ |
| 队友（双方**都已锁题**） | ✅ | ✅ |
| 队友（任一方未锁题） | ❌ | ❌ |
| **对手（比赛中）** | ❌ | ❌ |
| 旁观者（未参赛/匿名） | ✅ | ❌ |
| 比赛结束后 | ✅ | 仅本人 |

实测验证：

```
未锁题：  匿名旁观 2 条 | 对手 0 条 | 队友只看到自己 1 条
         队友查详情 403，匿名查详情 restricted=True（无代码、无测试点）
均锁题：  队友 2 条且可看代码+13 个测试点；对手仍 0 条
赛后：    匿名可见 2 条，但仍拿不到代码
```

这套规则同时作用于 `/api/submissions`、`/api/submission/{id}`
和它的 SSE 流，避免绕过接口拿数据。

Hack 详情也有对应的隔离：比赛期间只有攻防双方和管理员能看到 Hack 数据与运行
详情，其他人只能看到判定结果；比赛结束后全部公开。
