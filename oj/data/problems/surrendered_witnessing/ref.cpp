#include <bits/stdc++.h>
using namespace std;
const int N = 3e5 + 5;
typedef int arr[N];
int n, m, Ans;
char s[N];
arr L, R, fa, tag, Cant, Cost, Size;
inline int Gf(int x) {
    if (!fa[x])
        return x;
    if (!fa[fa[x]]) // 跳过根节点的tag
        return fa[x];
    int p = Gf(fa[x]);
    tag[x] ^= tag[fa[x]];
    return fa[x] = p;
}
inline void Merge(int a, int b) {
    fa[a] = b, 
    Size[b] += Size[a], 
    Cost[b] += Cost[a], 
    Cant[b] |= Cant[a],
    tag[a] ^= tag[b];
}
inline int op(int x) { return tag[x] ^ tag[fa[x]]; }
inline int Calc(int i) {
    if (!L[i])
        return Ans;
    if (!R[i]) {
        int x = Gf(L[i]);
        Cant[x] = 1;
        if (op(L[i]) == (s[i] - '0'))
            Ans += Cost[x], tag[x] ^= 1, Cost[x] = -Cost[x];
        return Ans;
    }
    int x = Gf(L[i]), y = Gf(R[i]);
    if (Size[x] > Size[y])
        swap(x, y);
    if (x == y)
        return Ans;
    if ((op(L[i]) ^ op(R[i])) == s[i] - '0') {
        int Cx = Cost[x], Cy = Cost[y];
        if ((Cx < Cy && !Cant[x]) || Cant[y])
            Ans += Cx, tag[x] ^= 1, Cost[x] = -Cx;
        else
            Ans += Cy, tag[y] ^= 1, Cost[y] = -Cy;
    }
    Merge(x, y);
    return Ans;
}
int main() {
    scanf("%d%d%s", &n, &m, s + 1);
    for (int i = 1, c; i <= m; ++i) {
        scanf("%d", &c);
        for (int x; c--;)
            scanf("%d", &x), L[x] ? R[x] = i : L[x] = i;
    }
    for (int i = 1; i <= m; ++i)
        Size[i] = Cost[i] = 1;
    for (int i = 1; i <= n; ++i)
        printf("%d\n", Calc(i));
    return 0;
}
