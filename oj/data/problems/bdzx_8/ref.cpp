#include <iostream>
#include <cstdio>
#include <algorithm>

using namespace std;

const int MOD = 1000000007;

// FHQ Treap 节点定义
struct Node {
    int l, r, sz, rev;
    unsigned int rnd;
    int val[2]; // val[0] = b (常数项), val[1] = a (一次项)
    int prod[30]; // 维护子树的多项式乘积
} tr[200005];

// 极速伪随机数生成器 (供 Treap 使用)
inline unsigned int xorshift() {
    static unsigned int x = 123456789;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

// 快读
inline int read() {
    int x = 0; char c = getchar();
    while (c < '0' || c > '9') c = getchar();
    while (c >= '0' && c <= '9') x = x * 10 + c - '0', c = getchar();
    return x;
}

// 经过模板展开优化的 Pushup 操作
template<int K>
inline void pushup_opt(int u) {
    tr[u].sz = tr[tr[u].l].sz + 1 + tr[tr[u].r].sz;
    int temp[K] = {0};
    
    // 第一步：先将 左子树乘积 乘上 当前节点的一次多项式 (O(K) 时间)
    if (tr[u].l) {
        for (int i = 0; i < K; ++i) {
            if (!tr[tr[u].l].prod[i]) continue;
            temp[i] = (temp[i] + 1LL * tr[tr[u].l].prod[i] * tr[u].val[0]) % MOD;
            int nxt = (i + 1 == K) ? 0 : (i + 1);
            temp[nxt] = (temp[nxt] + 1LL * tr[tr[u].l].prod[i] * tr[u].val[1]) % MOD;
        }
    } else {
        temp[0] = tr[u].val[0];
        if constexpr (K > 1) temp[1] = tr[u].val[1];
        else temp[0] = (temp[0] + tr[u].val[1]) % MOD;
    }
    
    // 第二步：将 前缀结果 乘上 右子树乘积 (O(K^2) 时间)
    if (tr[u].r) {
        unsigned long long tmp_mul[K] = {0};
        const int *A = temp;
        const int *B = tr[tr[u].r].prod;
        
        for (int i = 0; i < K; ++i) {
            if (!A[i]) continue;
            for (int j = 0; j < K - i; ++j) tmp_mul[i + j] += 1ULL * A[i] * B[j];
            for (int j = K - i; j < K; ++j) tmp_mul[i + j - K] += 1ULL * A[i] * B[j];
            // 防止 tmp_mul[j] 超过 ULLONG_MAX
            if constexpr (K > 15) {
                if (i == 15) {
                    for (int j = 0; j < K; ++j) tmp_mul[j] %= MOD;
                }
            }
        }
        for (int i = 0; i < K; ++i) tr[u].prod[i] = tmp_mul[i] % MOD;
    } else {
        for (int i = 0; i < K; ++i) tr[u].prod[i] = temp[i];
    }
}

// 封装 Treap
template<int K>
struct Treap {
    int root, tot;
    
    inline int new_node(int a, int b) {
        int u = ++tot;
        tr[u].l = tr[u].r = 0;
        tr[u].sz = 1;
        tr[u].rev = 0;
        tr[u].rnd = xorshift();
        tr[u].val[0] = b % MOD;
        tr[u].val[1] = a % MOD;
        for(int i = 0; i < K; ++i) tr[u].prod[i] = 0;
        
        tr[u].prod[0] = tr[u].val[0];
        if constexpr (K > 1) tr[u].prod[1] = tr[u].val[1];
        else tr[u].prod[0] = (tr[u].prod[0] + tr[u].val[1]) % MOD;
        return u;
    }
    
    inline void pushdown(int u) {
        if (tr[u].rev) {
            // 注意：由于多项式乘法满足交换律，区间翻转只需影响结构，不需要更改 prod!
            std::swap(tr[u].l, tr[u].r);
            if (tr[u].l) tr[tr[u].l].rev ^= 1;
            if (tr[u].r) tr[tr[u].r].rev ^= 1;
            tr[u].rev = 0;
        }
    }
    
    void split(int u, int k_sz, int &x, int &y) {
        if (!u) { x = y = 0; return; }
        pushdown(u);
        if (tr[tr[u].l].sz + 1 <= k_sz) {
            x = u;
            split(tr[u].r, k_sz - tr[tr[u].l].sz - 1, tr[u].r, y);
            pushup_opt<K>(x);
        } else {
            y = u;
            split(tr[u].l, k_sz, x, tr[u].l);
            pushup_opt<K>(y);
        }
    }
    
    int merge(int x, int y) {
        if (!x || !y) return x | y;
        pushdown(x); pushdown(y);
        if (tr[x].rnd < tr[y].rnd) {
            tr[x].r = merge(tr[x].r, y);
            pushup_opt<K>(x);
            return x;
        } else {
            tr[y].l = merge(x, tr[y].l);
            pushup_opt<K>(y);
            return y;
        }
    }
    
    inline void insert(int pos, int a, int b) {
        int x, y;
        split(root, pos - 1, x, y);
        root = merge(merge(x, new_node(a, b)), y);
    }
    
    inline void reverse(int l, int r) {
        int x, y, z;
        split(root, l - 1, x, y);
        split(y, r - l + 1, y, z);
        if (y) tr[y].rev ^= 1;
        root = merge(merge(x, y), z);
    }
    
    inline int query(int l, int r, int c) {
        int x, y, z;
        split(root, l - 1, x, y);
        split(y, r - l + 1, y, z);
        int ans = tr[y].prod[c];
        root = merge(merge(x, y), z);
        return ans;
    }
    
    void solve(int q) {
        root = tot = 0;
        int lst = 0;
        for (int i = 0; i < q; ++i) {
            int op = read();
            if (op == 1) {
                int pos = read(), a = read(), b = read();
                pos ^= lst; a ^= lst; b ^= lst;
                insert(pos, a, b);
            } else if (op == 2) {
                int l = read(), r = read();
                l ^= lst; r ^= lst;
                reverse(l, r);
            } else if (op == 3) {
                int l = read(), r = read(), c = read();
                l ^= lst; r ^= lst; c ^= lst;
                lst = query(l, r, c);
                printf("%d\n", lst);
            }
        }
    }
};

int main() {
    int k = read(), q = read();
    switch (k) {
        case 2:  { Treap<2> t; t.solve(q); break; }
        case 7:  { Treap<7> t; t.solve(q); break; }
        case 14: { Treap<14> t; t.solve(q); break; }
        case 18: { Treap<18> t; t.solve(q); break; }
        case 20: { Treap<20> t; t.solve(q); break; }
        case 21: { Treap<21> t; t.solve(q); break; }
        case 22: { Treap<22> t; t.solve(q); break; }
        case 25: { Treap<25> t; t.solve(q); break; }
        case 26: { Treap<26> t; t.solve(q); break; }
        case 27: { Treap<27> t; t.solve(q); break; }
        case 30: { Treap<30> t; t.solve(q); break; }
        default: { Treap<30> t; t.solve(q); break; } // 安全回调
    }
    return 0;
}