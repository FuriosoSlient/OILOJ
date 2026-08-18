#include <bits/stdc++.h>
#define int long long

#define F(i, a, b) for (int i = (a); i <= (b); i++)
#define dF(i, a, b) for (int i = (a); i >= (b); i--)
using namespace std;

typedef long long ll;
typedef pair<int, int> pii;

const int N = 1000005, M = (N << 1), inf = 1e16, mod = 1e9 + 7;
int n, m, cnt, mn[N][2], mx[N][2];
vector<int> g[N][2], an;
int dfs(int u) {
    int now = ++ cnt;
    if (g[now][0].size())
        if (mn[now][0] <= cnt || !dfs(mx[now][0]))
            return 0;
    an.push_back(now);
    if (g[now][1].size()) {
        if (mn[now][1] <= cnt || !dfs(max(u, mx[now][1])))
            return 0;
    } else if (cnt < u && !dfs(u)) return 0;
    return 1;
}
signed main() {
    ios_base::sync_with_stdio(0);
    cin.tie(0), cout.tie(0);
    cin >> n >> m;
    F(i, 1, m) {
        int x, y;
        string s;
        cin >> x >> y >> s;
        g[x][s[0] == 'R'].push_back(y);
    }
    F(i, 1, n) {
        sort(g[i][0].begin(), g[i][0].end());
        if (g[i][0].size()) 
            mn[i][0] = g[i][0][0], mx[i][0] = g[i][0].back();
        sort(g[i][1].begin(), g[i][1].end());
        if (g[i][1].size()) 
            mn[i][1] = g[i][1][0], mx[i][1] = g[i][1].back();
    }
    if (dfs(n)) {
        for (auto i : an) cout << i << ' ';
    } else cout << "IMPOSSIBLE";
    return 0;
}

