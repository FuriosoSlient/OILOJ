#include "testlib.h"
#include <vector>
#include <string>

using namespace std;

struct Constraint {
    int a, b;
    string dir;
};

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    // 1. 读取输入数据 (inf)
    int n = inf.readInt();
    int c = inf.readInt();

    vector<Constraint> constraints(c);
    for (int i = 0; i < c; ++i) {
        constraints[i].a = inf.readInt();
        constraints[i].b = inf.readInt();
        constraints[i].dir = inf.readToken();
    }

    // 2. 读取标准答案的第一项 (ans)
    string j_first = ans.readToken();
    bool jury_has_sol = (j_first != "IMPOSSIBLE");

    // 3. 读取选手输出的第一项 (ouf)
    string p_first = ouf.readToken();
    bool participant_has_sol = (p_first != "IMPOSSIBLE");

    // 4. 处理无解的情况
    if (!participant_has_sol) {
        if (jury_has_sol) {
            quitf(_wa, "Participant reported IMPOSSIBLE, but a valid tree exists");
        }
        quitf(_ok, "Correctly identified as IMPOSSIBLE");
    }

    // 5. 选手输出了方案，读取完整的中序遍历序列
    vector<int> in_order(n + 1);
    vector<bool> used(n + 1, false);

    // 解析第一个整数
    try {
        size_t idx = 0;
        int val = stoi(p_first, &idx);
        if (idx != p_first.size() || val < 1 || val > n) {
            quitf(_wa, "Invalid first node in inorder traversal: '%s'", p_first.c_str());
        }
        in_order[1] = val;
        used[val] = true;
    } catch (...) {
        quitf(_wa, "Invalid first node in inorder traversal: '%s'", p_first.c_str());
    }

    // 读取剩下的 n - 1 个整数
    for (int i = 2; i <= n; ++i) {
        in_order[i] = ouf.readInt(1, n, "inorder[i]");
        if (used[in_order[i]]) {
            quitf(_wa, "Duplicate node %d found in inorder traversal", in_order[i]);
        }
        used[in_order[i]] = true;
    }

    // 检查选手是否输出了多余的内容
    ouf.readEof();

    // 6. 根据前序遍历 (1..n) 和选手给出的中序遍历重建二叉树 (O(n) 单调栈算法)
    vector<int> lc(n + 1, 0), rc(n + 1, 0);
    vector<int> st;
    st.reserve(n + 1);

    int in_ptr = 1;
    for (int u = 1; u <= n; ++u) {
        int last = 0;
        while (!st.empty() && st.back() == in_order[in_ptr]) {
            last = st.back();
            st.pop_back();
            in_ptr++;
        }
        if (last != 0) {
            rc[last] = u;
        } else if (!st.empty()) {
            lc[st.back()] = u;
        }
        st.push_back(u);
    }

    while (!st.empty() && st.back() == in_order[in_ptr]) {
        st.pop_back();
        in_ptr++;
    }

    // 如果中序遍历未能完全匹配，说明该中序遍历与前序 1..n 冲突
    if (in_ptr != n + 1 || !st.empty()) {
        quitf(_wa, "Given inorder traversal does not form a valid binary tree with preorder 1..n");
    }

    // 7. 计算子树大小并验证前序遍历的区间连续性
    vector<int> sz(n + 1, 1);
    for (int u = n; u >= 1; --u) {
        if (lc[u]) sz[u] += sz[lc[u]];
        if (rc[u]) sz[u] += sz[rc[u]];
    }

    for (int u = 1; u <= n; ++u) {
        if (lc[u] != 0 && lc[u] != u + 1) {
            quitf(_wa, "Tree preorder structure violated at node %d (left child = %d, expected %d)", u, lc[u], u + 1);
        }
        if (rc[u] != 0) {
            int expected_rc = u + 1 + (lc[u] ? sz[lc[u]] : 0);
            if (rc[u] != expected_rc) {
                quitf(_wa, "Tree preorder structure violated at node %d (right child = %d, expected %d)", u, rc[u], expected_rc);
            }
        }
    }

    // 8. 校验所有 c 个约束条件
    for (int i = 0; i < c; ++i) {
        int a = constraints[i].a;
        int b = constraints[i].b;
        const string& dir = constraints[i].dir;

        if (dir == "LEFT") {
            if (lc[a] == 0) {
                quitf(_wa, "Constraint %d failed: node %d has no left child, but node %d must be in left subtree", i + 1, a, b);
            }
            int l = lc[a];
            int r = lc[a] + sz[lc[a]] - 1;
            if (b < l || b > r) {
                quitf(_wa, "Constraint %d failed: node %d is not in left subtree of %d (valid left range is [%d, %d])", i + 1, b, a, l, r);
            }
        } else if (dir == "RIGHT") {
            if (rc[a] == 0) {
                quitf(_wa, "Constraint %d failed: node %d has no right child, but node %d must be in right subtree", i + 1, a, b);
            }
            int l = rc[a];
            int r = rc[a] + sz[rc[a]] - 1;
            if (b < l || b > r) {
                quitf(_wa, "Constraint %d failed: node %d is not in right subtree of %d (valid right range is [%d, %d])", i + 1, b, a, l, r);
            }
        }
    }

    // 9. 如果标准答案输出了 IMPOSSIBLE 但选手找出了合法解
    if (!jury_has_sol) {
        quitf(_fail, "Participant found a valid tree, but jury output was IMPOSSIBLE");
    }

    quitf(_ok, "Tree is valid, matches preorder 1..n and satisfies all %d constraints", c);
    return 0;
}