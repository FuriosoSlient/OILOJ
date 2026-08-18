#include "testlib.h"
#include <vector>
#include <algorithm>
using namespace std;

// Perfect heap-indexed tree: parent(i)=i/2, labels p[1..n].
// Input file: h, then n=2^h-1 labels in heap order.

int n;
vector<int> p, pos;

int up(int x) { return x / 2; }

int lca_heap(int a, int b) {
    while (a != b) {
        if (a > b) a = up(a);
        else b = up(b);
    }
    return a;
}

// Nodes on the unique path a--b (heap indices).
vector<int> path_nodes(int a, int b) {
    int g = lca_heap(a, b);
    vector<int> left, right;
    for (int x = a; x != g; x = up(x)) left.push_back(x);
    left.push_back(g);
    for (int x = b; x != g; x = up(x)) right.push_back(x);
    reverse(right.begin(), right.end());
    left.insert(left.end(), right.begin(), right.end());
    return left;
}

int dist_heap(int a, int b) {
    int g = lca_heap(a, b);
    int d = 0;
    for (int x = a; x != g; x = up(x)) d++;
    for (int x = b; x != g; x = up(x)) d++;
    return d;
}

// LCA of labels u,v when the tree is rooted at label w.
int query_lca(int lu, int lv, int lw) {
    int u = pos[lu], v = pos[lv], w = pos[lw];
    auto path = path_nodes(u, v);
    int best = path[0], bestd = dist_heap(w, path[0]);
    for (int x : path) {
        int d = dist_heap(w, x);
        if (d < bestd) { bestd = d; best = x; }
    }
    return p[best];
}

int main(int argc, char* argv[]) {
    registerInteraction(argc, argv);

    int h = inf.readInt(3, 18, "h");
    n = (1 << h) - 1;
    p.assign(n + 1, 0);
    pos.assign(n + 1, 0);
    vector<int> used(n + 1, 0);
    for (int i = 1; i <= n; i++) {
        p[i] = inf.readInt(1, n, "label");
        if (used[p[i]])
            quitf(_fail, "duplicate label %d in secret permutation", p[i]);
        used[p[i]] = 1;
        pos[p[i]] = i;
    }

    // Contestant only sees h.
    cout << h << endl;
    cout.flush();

    int limit = n + 420;
    int queries = 0;
    while (true) {
        string cmd = ouf.readToken();
        if (cmd == "?") {
            queries++;
            if (queries > limit) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "too many queries (%d > %d)", queries, limit);
            }
            int u = ouf.readInt();
            int v = ouf.readInt();
            int w = ouf.readInt();
            if (u < 1 || u > n || v < 1 || v > n || w < 1 || w > n
                || u == v || u == w || v == w) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "invalid query ? %d %d %d", u, v, w);
            }
            int ans = query_lca(u, v, w);
            cout << ans << endl;
            cout.flush();
        } else if (cmd == "!") {
            int r = ouf.readInt();
            if (r == p[1])
                quitf(_ok, "found root %d after %d queries", r, queries);
            quitf(_wa, "wrong root: reported %d, expected %d", r, p[1]);
        } else {
            cout << -1 << endl;
            cout.flush();
            quitf(_wa, "expected ? or !, got '%s'", cmd.c_str());
        }
    }
}
