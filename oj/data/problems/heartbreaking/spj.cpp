#include "testlib.h"
#include <vector>
#include <string>
using namespace std;

struct Constraint { int a, b; string dir; };

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);
    int n = inf.readInt();
    int c = inf.readInt();
    vector<Constraint> constraints(c);
    for (int i = 0; i < c; ++i) {
        constraints[i].a = inf.readInt();
        constraints[i].b = inf.readInt();
        constraints[i].dir = inf.readToken();
    }

    string j_first = ans.readToken();
    bool jury_has_sol = (j_first != "IMPOSSIBLE");
    string p_first = ouf.readToken();
    bool participant_has_sol = (p_first != "IMPOSSIBLE");

    if (!participant_has_sol) {
        if (jury_has_sol)
            quitf(_wa, "Participant reported IMPOSSIBLE, but a valid tree exists");
        quitf(_ok, "Correctly identified as IMPOSSIBLE");
    }

    vector<int> in_order(n + 1);
    vector<bool> used(n + 1, false);
    try {
        size_t idx = 0;
        int val = stoi(p_first, &idx);
        if (idx != p_first.size() || val < 1 || val > n)
            quitf(_wa, "Invalid first node: '%s'", p_first.c_str());
        in_order[1] = val;
        used[val] = true;
    } catch (...) {
        quitf(_wa, "Invalid first node: '%s'", p_first.c_str());
    }
    for (int i = 2; i <= n; ++i) {
        in_order[i] = ouf.readInt(1, n, "inorder[i]");
        if (used[in_order[i]])
            quitf(_wa, "Duplicate node %d", in_order[i]);
        used[in_order[i]] = true;
    }

    vector<int> lc(n + 1, 0), rc(n + 1, 0);
    vector<int> st;
    int in_ptr = 1;
    for (int u = 1; u <= n; ++u) {
        int last = 0;
        while (!st.empty() && st.back() == in_order[in_ptr]) {
            last = st.back();
            st.pop_back();
            in_ptr++;
        }
        if (last != 0) rc[last] = u;
        else if (!st.empty()) lc[st.back()] = u;
        st.push_back(u);
    }
    while (!st.empty() && st.back() == in_order[in_ptr]) {
        st.pop_back();
        in_ptr++;
    }
    if (in_ptr != n + 1 || !st.empty())
        quitf(_wa, "Inorder does not form a valid tree with preorder 1..n");

    vector<int> sz(n + 1, 1);
    for (int u = n; u >= 1; --u) {
        if (lc[u]) sz[u] += sz[lc[u]];
        if (rc[u]) sz[u] += sz[rc[u]];
    }

    for (int i = 0; i < c; ++i) {
        int a = constraints[i].a, b = constraints[i].b;
        const string& dir = constraints[i].dir;
        if (dir == "LEFT") {
            if (!lc[a]) quitf(_wa, "node %d has no left child", a);
            int l = lc[a], r = lc[a] + sz[lc[a]] - 1;
            if (b < l || b > r) quitf(_wa, "node %d not in left subtree of %d", b, a);
        } else if (dir == "RIGHT") {
            if (!rc[a]) quitf(_wa, "node %d has no right child", a);
            int l = rc[a], r = rc[a] + sz[rc[a]] - 1;
            if (b < l || b > r) quitf(_wa, "node %d not in right subtree of %d", b, a);
        }
    }
    if (!jury_has_sol)
        quitf(_fail, "Participant found a valid tree, jury said IMPOSSIBLE");
    quitf(_ok, "valid tree");
}
