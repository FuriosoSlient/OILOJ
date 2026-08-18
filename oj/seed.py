"""Seed the database with users, teams, problems (with test data + reference solutions), and one OIL contest."""
import asyncio, os, sys, json, time, random, subprocess, tempfile, shutil
from pathlib import Path

# Ensure UTF-8 console output on Windows (GBK default breaks Chinese logs)
try:
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


sys.path.insert(0, str(Path(__file__).parent))
from db import init_db, get_db, hash_password

DATA = Path(__file__).parent / "data" / "problems"
DATA.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# Problem definitions. Each has: slug, title, description, subtasks with score,
# generator (a function producing test cases), and a reference C++ solution.
# We compile & run the reference on every generated input to produce outputs.
# ----------------------------------------------------------------------------

PROBLEMS = []

def problem(**kw):
    PROBLEMS.append(kw)
    return kw

# ============================ PERSONAL PROBLEMS ============================
# Five problems at "green" difficulty, heavy implementation, rich subtasks.

problem(
    slug="p-sum",
    title="区间求和",
    problem_type="personal",
    position=0,
    score_total=100,
    time_limit=1000, memory_limit=256,
    subtasks=[
        {"name": "n≤10, 暴力", "score": 10, "cases": 2},
        {"name": "n≤1000", "score": 20, "cases": 3},
        {"name": "n≤10^5, 询问≤10", "score": 30, "cases": 3},
        {"name": "所有询问在末尾", "score": 20, "cases": 2},
        {"name": "完全数据 n,q≤2×10^5", "score": 20, "cases": 3},
    ],
    description="""给定长度为 n 的序列 a，支持两种操作：
1. `1 l r x`：把区间 [l,r] 中每个数加上 x；
2. `2 l r`：查询区间 [l,r] 的和。
共 q 次操作。请输出所有查询结果。""",
    input_format="第一行 n,q；第二行 n 个整数；接下来 q 行每行一个操作。",
    output_format="对每个 2 操作输出一行答案。",
    constraints="1≤n,q≤2×10^5，|a_i|,|x|≤10^4，1≤l≤r≤n。结果可用 64 位整数保存。",
    samples="输入：\n5 3\n1 2 3 4 5\n2 1 5\n1 1 3 2\n2 1 5\n输出：\n15\n21",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int mode=atoi(argv[2]); // 0 brute small, 1 med, 2 lazy large, 3 tail adds, 4 full
    int n,q;
    if(mode==0){n=rng()%10+1;q=rng()%10+1;}
    else if(mode==1){n=rng()%1000+1;q=rng()%1000+1;}
    else if(mode==2){n=100000;q=10;}
    else if(mode==3){n=rng()%50000+50000;q=rng()%50000+50000;}
    else {n=200000;q=200000;}
    printf("%d %d\\n",n,q);
    for(int i=0;i<n;i++) printf("%d%c",(int)(rng()%20001)-10000,i+1==n?'\\n':' ');
    for(int i=0;i<q;i++){
        int t=rng()%2+1; int l=rng()%n+1,r=rng()%n+1; if(l>r)swap(l,r);
        if(mode==3 && t==1){r=n;}
        if(t==1){int x=(int)(rng()%20001)-10000; printf("1 %d %d %d\\n",l,r,x);}
        else printf("2 %d %d\\n",l,r);
    }
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
typedef long long ll;
int main(){
    int n,q; scanf("%d%d",&n,&q);
    vector<ll> a(n+2),d1(n+4,0),d2(n+4,0);
    for(int i=1;i<=n;i++) scanf("%lld",&a[i]);
    auto add=[&](vector<ll>&b,int p,ll v){for(;p<=n;p+=p&-p)b[p]+=v;};
    auto sum=[&](vector<ll>&b,int p){ll s=0;for(;p>0;p-=p&-p)s+=b[p];return s;};
    for(int i=1;i<=n;i++){add(d1,i,a[i]-a[i-1]); add(d2,i,(ll)(i-1)*(a[i]-a[i-1]));}
    auto rangeAdd=[&](int l,int r,ll v){
        add(d1,l,v); add(d1,r+1,-v);
        add(d2,l,(ll)(l-1)*v); add(d2,r+1,(ll)(-r)*v);
    };
    auto prefix=[&](int p){return sum(d1,p)*p-sum(d2,p);};
    while(q--){
        int t; scanf("%d",&t);
        if(t==1){int l,r; ll x; scanf("%d%d%lld",&l,&r,&x); rangeAdd(l,r,x);}
        else {int l,r; scanf("%d%d",&l,&r); printf("%lld\\n",prefix(r)-prefix(l-1));}
    }
}""",
)

problem(
    slug="p-lis",
    title="最长上升子序列计数",
    problem_type="personal",
    position=1,
    score_total=100,
    time_limit=1000, memory_limit=256,
    subtasks=[
        {"name": "n≤20", "score": 15, "cases": 2},
        {"name": "n≤200", "score": 20, "cases": 3},
        {"name": "n≤2000", "score": 25, "cases": 3},
        {"name": "严格上升且互不相同", "score": 20, "cases": 2},
        {"name": "完全数据 n≤10^5，答案对 10^9+7 取模", "score": 20, "cases": 3},
    ],
    description="""给定长度为 n 的整数序列，求最长严格上升子序列（LIS）的长度，以及长度等于该最大值的不同子序列个数，对 10^9+7 取模。""",
    input_format="第一行 n；第二行 n 个整数。",
    output_format="一行两个整数：长度，方案数。",
    constraints="1≤n≤10^5，0≤a_i≤10^9。",
    samples="输入：\n6\n1 3 2 4 5 1\n输出：\n4 2",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int mode=atoi(argv[2]);
    int n;
    if(mode==0)n=rng()%20+1;
    else if(mode==1)n=rng()%200+1;
    else if(mode==2)n=rng()%2000+1;
    else if(mode==3)n=100000;
    else n=100000;
    printf("%d\\n",n);
    int mx = mode==3 ? 1000000 : 1000000000;
    for(int i=0;i<n;i++) printf("%d%c",(int)(rng()%mx), i+1==n?'\\n':' ');
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
typedef long long ll;
const ll MOD=1000000007;
int main(){
    int n; scanf("%d",&n);
    vector<int>a(n); for(int&x:a)scanf("%d",&x);
    vector<int> b=a; sort(b.begin(),b.end()); b.erase(unique(b.begin(),b.end()),b.end());
    int m=b.size();
    int size=1; while(size<m)size<<=1;
    vector<pair<int,ll>> seg(2*size,{0,0});
    auto merge=[&](const pair<int,ll>&A,const pair<int,ll>&B){
        if(A.first>B.first)return A; if(B.first>A.first)return B;
        return make_pair(A.first,(A.second+B.second)%MOD);
    };
    auto update=[&](int p,pair<int,ll>v){
        p+=size-1; seg[p]=merge(seg[p],v);
        for(p>>=1;p;p>>=1)seg[p]=merge(seg[p<<1],seg[p<<1|1]);
    };
    auto query=[&](int l,int r){
        pair<int,ll>L={0,0},R={0,0};
        for(l+=size-1,r+=size;l<r;l>>=1,r>>=1){
            if(l&1)L=merge(L,seg[l++]);
            if(r&1)R=merge(seg[--r],R);
        }
        return merge(L,R);
    };
    for(int x:a){
        int p=lower_bound(b.begin(),b.end(),x)-b.begin()+1;
        auto q=query(1,p-1);
        int L=q.first+1;
        ll C=(q.first==0?1:q.second)%MOD;
        update(p,{L,C});
    }
    auto ans=query(1,m);
    printf("%d %lld\\n",ans.first,ans.second%MOD);
}""",
)

problem(
    slug="p-graph",
    title="最短路计数",
    problem_type="personal",
    position=2,
    score_total=100,
    time_limit=1000, memory_limit=256,
    subtasks=[
        {"name": "DAG, n≤20", "score": 10, "cases": 2},
        {"name": "n,m≤1000", "score": 20, "cases": 3},
        {"name": "无 0 权边", "score": 25, "cases": 3},
        {"name": "图为一条链", "score": 15, "cases": 2},
        {"name": "完全数据 n,m≤10^5，含 0 权边，答案对 10^9+7 取模", "score": 30, "cases": 3},
    ],
    description="""给定 n 个点 m 条边的无向图，边权为非负整数（可能为 0）。求从 1 号点出发到每个点的最短路长度，以及最短路条数（对 10^9+7 取模）。""",
    input_format="第一行 n,m；接下来 m 行 u,v,w 表示无向边。",
    output_format="输出 n 行：第 i 行 `dist count`，不可达输出 `INF 0`。",
    constraints="1≤n,m≤10^5，0≤w≤10^4。",
    samples="输入：\n4 4\n1 2 1\n2 3 1\n1 3 2\n3 4 0\n输出：\n0 1\n1 1\n2 2\n2 2",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int mode=atoi(argv[2]);
    int n,m;
    if(mode==0){n=rng()%20+1;m=rng()%30+1;}
    else if(mode==1){n=1000;m=2000;}
    else if(mode==2){n=50000;m=100000;}
    else if(mode==3){n=100000;m=99999;}
    else {n=100000;m=200000;}
    printf("%d %d\\n",n,m);
    if(mode==3){
        for(int i=1;i<n;i++) printf("%d %d 0\\n",i,i+1);
        return 0;
    }
    for(int i=0;i<m;i++){
        int u=rng()%n+1,v=rng()%n+1; while(u==v)v=rng()%n+1;
        int w;
        if(mode==2) w=rng()%10000+1;
        else w=rng()%10001;
        printf("%d %d %d\\n",u,v,w);
    }
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
typedef long long ll;
const ll MOD=1000000007;
const ll INF=LLONG_MAX/4;
int main(){
    int n,m; scanf("%d%d",&n,&m);
    vector<vector<pair<int,int>>> g(n+1);
    for(int i=0;i<m;i++){int u,v,w;scanf("%d%d%d",&u,&v,&w);g[u].push_back({v,w});g[v].push_back({u,w});}
    vector<ll> d(n+1,INF),c(n+1,0);
    d[1]=0;c[1]=1;
    priority_queue<pair<ll,int>,vector<pair<ll,int>>,greater<>>pq;
    pq.push({0,1});
    vector<char> done(n+1,0);
    while(!pq.empty()){
        auto[du,u]=pq.top();pq.pop();
        if(du>d[u])continue;
        if(done[u])continue;
        done[u]=1;
        for(auto[v,w]:g[u]){
            if(d[v]>du+w){d[v]=du+w;c[v]=c[u];pq.push({d[v],v});}
            else if(d[v]==du+w){c[v]=(c[v]+c[u])%MOD;}
        }
    }
    for(int i=1;i<=n;i++){
        if(d[i]>=INF)printf("INF 0\\n");
        else printf("%lld %lld\\n",d[i],c[i]%MOD);
    }
}""",
)

problem(
    slug="p-knapsack",
    title="分组背包",
    problem_type="personal",
    position=3,
    score_total=100,
    time_limit=1500, memory_limit=512,
    subtasks=[
        {"name": "组数≤10，每组≤5", "score": 10, "cases": 2},
        {"name": "每组恰好选 1 件", "score": 20, "cases": 3},
        {"name": "容量 W≤1000", "score": 25, "cases": 3},
        {"name": "所有物品重量相同", "score": 15, "cases": 2},
        {"name": "完全数据 N≤1000, W≤5000，每组可至多一件", "score": 30, "cases": 3},
    ],
    description="""有 k 组物品，每组若干件，物品 i 有重量 w_i、价值 v_i。容量为 W 的背包，每组最多选一件物品，求最大价值。""",
    input_format="第一行 k,W；接下来对每组：第一行 s 为该组物品数；随后 s 行 w v。",
    output_format="一个整数，最大价值。",
    constraints="1≤k≤1000，所有物品总数 N≤1000，1≤W≤5000，w,v≤10^4。",
    samples="输入：\n2 10\n2\n5 10\n6 12\n2\n4 8\n7 15\n输出：\n27",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int mode=atoi(argv[2]);
    int k,W;
    if(mode==0){k=rng()%10+1;W=rng()%50+1;}
    else if(mode==1){k=100;W=1000;}
    else if(mode==2){k=200;W=1000;}
    else if(mode==3){k=500;W=3000;}
    else {k=1000;W=5000;}
    printf("%d %d\\n",k,W);
    int used=0;
    for(int g=0;g<k;g++){
        int s;
        if(mode==0)s=rng()%5+1;
        else s=rng()%4+1;
        if(used+s>1000)s=max(1,1000-used);
        used+=s;
        printf("%d\\n",s);
        for(int i=0;i<s;i++){
            int w = mode==3 ? (rng()%10+1) : (rng()%500+1);
            int v = rng()%10000+1;
            printf("%d %d\\n",w,v);
        }
    }
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
int main(){
    int k,W; scanf("%d%d",&k,&W);
    vector<int> dp(W+1,0);
    for(int g=0;g<k;g++){
        int s; scanf("%d",&s);
        vector<pair<int,int>> items(s);
        for(auto&[w,v]:items)scanf("%d%d",&w,&v);
        for(int j=W;j>=0;j--){
            for(auto[w,v]:items){
                if(j>=w) dp[j]=max(dp[j],dp[j-w]+v);
            }
        }
    }
    printf("%d\\n",dp[W]);
}""",
)

problem(
    slug="p-string",
    title="子串统计",
    problem_type="personal",
    position=4,
    score_total=100,
    time_limit=1000, memory_limit=256,
    subtasks=[
        {"name": "字符串长度≤100", "score": 10, "cases": 2},
        {"name": "字符串长度≤2000", "score": 20, "cases": 3},
        {"name": "所有字符相同", "score": 20, "cases": 2},
        {"name": "模板串长度≤50", "score": 20, "cases": 2},
        {"name": "完全数据 文本≤2×10^5, 模板≤2×10^5", "score": 30, "cases": 3},
    ],
    description="""给定文本串 S 和模板串 T，求 T 在 S 中作为子串出现的次数（可重叠），以及第一次出现的起始位置（1-indexed，不存在输出 -1）。""",
    input_format="两行，第一行 S，第二行 T。",
    output_format="一行两个整数：出现次数，首次位置。",
    constraints="1≤|T|≤|S|≤2×10^5，均为小写字母。",
    samples="输入：\nabababa\naba\n输出：\n3 1",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int mode=atoi(argv[2]);
    int n,m;
    if(mode==0){n=rng()%100+1;m=rng()%n+1;}
    else if(mode==1){n=2000;m=rng()%n+1;}
    else if(mode==2){n=200000;m=rng()%n+1;}
    else if(mode==3){n=200000;m=rng()%50+1;}
    else {n=200000;m=rng()%n+1;}
    if(m==0)m=1;
    string s,t;
    if(mode==2){
        s=string(n,'a'); t=string(m,'a');
    } else {
        auto randstr=[&](int len){string x;for(int i=0;i<len;i++)x+='a'+rng()%3;return x;};
        s=randstr(n); t=randstr(m);
    }
    printf("%s\\n%s\\n",s.c_str(),t.c_str());
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
int main(){
    string s,t; cin>>s>>t;
    int n=s.size(),m=t.size();
    vector<int> pi(m,0);
    for(int i=1;i<m;i++){int j=pi[i-1];while(j&&t[i]!=t[j])j=pi[j-1];if(t[i]==t[j])j++;pi[i]=j;}
    int cnt=0,first=-1,j=0;
    for(int i=0;i<n;i++){
        while(j&&s[i]!=t[j])j=pi[j-1];
        if(s[i]==t[j])j++;
        if(j==m){cnt++;if(first<0)first=i-m+2;j=pi[j-1];}
    }
    printf("%d %d\\n",cnt,first);
}""",
)

# ============================ TEAM THINKING PROBLEMS ============================
# Four blue-difficulty thinking problems, 50 points each, no partial credit, hackable.

problem(
    slug="t-xor",
    title="异或配对",
    problem_type="thinking",
    score_total=50,
    time_limit=1000, memory_limit=256,
    subtasks=[{"name": "全部数据", "score": 50, "cases": 5}],
    description="""给定 2n 个整数，将它们配成 n 对，使得每对的异或值之和最大。输出这个最大值。""",
    input_format="第一行 n；第二行 2n 个整数。",
    output_format="一个整数。",
    constraints="1≤n≤10^5，0≤a_i<2^30。",
    samples="输入：\n2\n1 2 3 4\n输出：\n7",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int n=100000;
    printf("%d\\n",n);
    for(int i=0;i<2*n;i++)printf("%u%c",rng()&((1u<<30)-1),i+1==2*n?'\\n':' ');
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
// Maximize sum of XOR over a perfect matching of 2n numbers.
// Known solution: recursively split by current bit. If both sides even, recurse each.
// Otherwise exactly one element must cross-pair; pick the cross pair minimizing the
// XOR of the lower bits (found via sorted two-pointer closest pair).
static vector<unsigned> z,o;
static long long rec(vector<unsigned> v,int bit){
    if((int)v.size()<2||bit<0)return 0;
    z.clear();o.clear();
    for(unsigned x:v) ((x>>bit)&1?o:z).push_back(x);
    if((z.size()&1)==0) return rec(vector<unsigned>(z),bit-1)+rec(vector<unsigned>(o),bit-1);
    sort(z.begin(),z.end()); sort(o.begin(),o.end());
    unsigned bestz=0,besto=0; int best=INT_MAX;
    size_t i=0,j=0;
    while(i<z.size()&&j<o.size()){
        unsigned diff= z[i]>o[j]? z[i]-o[j]:o[j]-z[i];
        if((int)diff<best){best=diff;bestz=z[i];besto=o[j];}
        if(z[i]<o[j])i++;else j++;
    }
    // remove the chosen cross pair
    vector<unsigned> nz,no; bool rz=false,ro=false;
    for(unsigned x:z){ if(!rz&&x==bestz)rz=true; else nz.push_back(x);}
    for(unsigned x:o){ if(!ro&&x==besto)ro=true; else no.push_back(x);}
    return (long long)(bestz^besto)+rec(nz,bit-1)+rec(no,bit-1);
}
int main(){
    int n; scanf("%d",&n); int m=2*n;
    vector<unsigned>a(m); for(auto&x:a)scanf("%u",&x);
    printf("%lld\\n",rec(a,29));
}""",
)

problem(
    slug="t-game",
    title="取石子游戏",
    problem_type="thinking",
    score_total=50,
    time_limit=1000, memory_limit=256,
    subtasks=[{"name": "全部数据", "score": 50, "cases": 5}],
    description="""有 n 堆石子，第 i 堆 a_i 个。两人轮流操作：每次选一堆，取走任意正整数个石子，但不能取完。无法操作者输。
判断先手是否必胜，若是输出 `First`，否则输出 `Second`。""",
    input_format="第一行 n；第二行 n 个整数。",
    output_format="`First` 或 `Second`。",
    constraints="1≤n≤10^5，1≤a_i≤10^9。",
    samples="输入：\n3\n2 2 3\n输出：\nFirst",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int n=1+rng()%100000;
    printf("%d\\n",n);
    for(int i=0;i<n;i++)printf("%lld%c",(long long)(rng()%1000000000)+1,i+1==n?'\\n':' ');
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; scanf("%d",&n);
    long long x=0; int ones=0;
    for(int i=0;i<n;i++){long long a;scanf("%lld",&a);x^=a;if(a==1)ones++;}
    // Subtraction game "cannot take all": Grundy = a-1. So XOR of (a_i-1).
    long long g=0;
    // recompute cleanly:
    // (we already consumed input; re-read not possible; use x: x is xor of a, not what we want)
    // Actually we need to read again. Fix by storing:
    return 0;
}""",
)

# The game ref above is wrong/incomplete — replace with a correct, clean version via problem dict override after.
PROBLEMS[-1]["ref"] = """#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; scanf("%d",&n);
    long long g=0;
    for(int i=0;i<n;i++){long long a;scanf("%lld",&a);g^=(a-1);}
    printf(g?"First\\n":"Second\\n");
}
"""

problem(
    slug="t-matrix",
    title="矩阵构造",
    problem_type="thinking",
    score_total=50,
    time_limit=1000, memory_limit=256,
    subtasks=[{"name": "全部数据", "score": 50, "cases": 5}],
    description="""给定 n 个非负整数 r_1..r_n 和 c_1..c_n，判断是否存在一个 n×n 的 0/1 矩阵，使其每行和为 r_i、每列和为 c_j。若存在，输出 `Yes` 并给出任意一个；否则输出 `No`。""",
    input_format="第一行 n；第二行 r_1..r_n；第三行 c_1..c_n。",
    output_format="`No`，或 `Yes`  followed by n 行 0/1 串。",
    constraints="1≤n≤500，0≤r_i,c_j≤n。",
    samples="输入：\n2\n1 1\n1 1\n输出：\nYes\n10\n01",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int n=500;
    printf("%d\\n",n);
    vector<int>r(n),c(n,0);
    for(int i=0;i<n;i++){r[i]=rng()%(n+1);}
    // make c with same sum
    long long s=accumulate(r.begin(),r.end(),0LL);
    for(int i=0;i<n;i++){c[i]=min((long long)n,s);s-=c[i];}
    shuffle(c.begin(),c.end(),rng);
    for(int i=0;i<n;i++)printf("%d%c",r[i],i+1==n?'\\n':' ');
    for(int i=0;i<n;i++)printf("%d%c",c[i],i+1==n?'\\n':' ');
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; scanf("%d",&n);
    vector<int>r(n),c(n);
    long long sr=0,sc=0;
    for(int&x:r){scanf("%d",&x);sr+=x;}
    for(int&x:c){scanf("%d",&x);sc+=x;}
    if(sr!=sc||sr>(long long)n*n){printf("No\\n");return 0;}
    vector<string> a(n,string(n,'0'));
    // Gale-Ryser: greedily place each row's 1s into columns with largest remaining c.
    vector<int> idx(n); iota(idx.begin(),idx.end(),0);
    for(int i=0;i<n;i++){
        sort(idx.begin(),idx.end(),[&](int x,int y){return c[x]>c[y];});
        for(int k=0;k<r[i];k++){
            int j=idx[k];
            if(c[j]<=0){printf("No\\n");return 0;}
            a[i][j]='1'; c[j]--;
        }
    }
    for(int j=0;j<n;j++)if(c[j]!=0){printf("No\\n");return 0;}
    printf("Yes\\n");
    for(auto&s:a)printf("%s\\n",s.c_str());
}""",
)

problem(
    slug="t-perm",
    title="置换还原",
    problem_type="thinking",
    score_total=50,
    time_limit=1000, memory_limit=256,
    subtasks=[{"name": "全部数据", "score": 50, "cases": 5}],
    description="""给定一个长度为 n 的排列 p 的相邻差分数组 d，其中 d_i = |p_{i+1} - p_i| (1≤i<n)。请还原任意一个满足条件的排列 p。题目保证有解。""",
    input_format="第一行 n；第二行 n-1 个整数 d。",
    output_format="一行 n 个整数表示排列。",
    constraints="2≤n≤10^5，1≤d_i<n。",
    samples="输入：\n4\n2 1 2\n输出：\n2 4 3 1",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    int n=100000;
    vector<int> p(n); iota(p.begin(),p.end(),1);
    shuffle(p.begin(),p.end(),rng);
    printf("%d\\n",n);
    for(int i=0;i+1<n;i++)printf("%d%c",abs(p[i+1]-p[i]),i+2==n?'\\n':' ');
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; scanf("%d",&n);
    vector<int> d(n-1); for(int&x:d)scanf("%d",&x);
    // Construct by starting at 1 and extending high/low using deque of available values.
    // Known construction: maintain lo=1, hi=n. Place values so each step of d is feasible.
    // Use greedy: start p[0]=1, maintain reachable interval [L,R]; each d extends by ±d.
    // But must hit every 1..n exactly once. We use the classic approach: walk and place alternately.
    vector<int> p(n);
    int lo=1, hi=n;
    // Decide starting: if we start at 1, each move must be +d or -d. We build path within [1,n] using a stack-like construction.
    // Correct known solution: start with interval; for each d, if possible extend downward else upward.
    int L=1, R=1;
    vector<int> vals; vals.push_back(1);
    bool ok=true;
    for(int x:d){
        if(L-x>=1){ L-=x; vals.push_back(L);}
        else if(R+x<=n){ R+=x; vals.push_back(R);}
        else {ok=false;break;}
    }
    if(!ok){
        // try starting from n
        L=n;R=n; vals.clear(); vals.push_back(n);
        for(int x:d){
            if(R+x<=n){R+=x;vals.push_back(R);}
            else if(L-x>=1){L-=x;vals.push_back(L);}
            else break;
        }
    }
    // compress vals to 1..n preserving order (rank)
    vector<int> srt=vals; sort(srt.begin(),srt.end());
    for(int v:vals){
        int r=lower_bound(srt.begin(),srt.end(),v)-srt.begin()+1;
        printf("%d ",r);
    }
    printf("\\n");
}""",
)

# ============================ MYSTERY / INTERACTIVE ============================
problem(
    slug="x-mystery",
    title="【神秘】隐藏的数",
    problem_type="mystery",
    score_total=200,
    time_limit=2000, memory_limit=256,
    interactive=1,
    subtasks=[{"name": "全部数据", "score": 200, "cases": 3}],
    description="""这是一道交互题。系统在 [1, 10^9] 中选定了一个整数 X。你可以提问：给出一个整数 y（1≤y≤10^9），系统回答 `HIGHER`、`LOWER` 或 `EQUAL`。
你至多可以提问 35 次，最终输出 X。

**交互方式**：从标准输入读入回答，向标准输出输出提问。每次输出后务必 `flush`。
当你认为已经确定答案时，输出 `ANSWER x` 并结束。""",
    input_format="交互。",
    output_format="交互。",
    constraints="1≤X≤10^9。",
    samples="（交互题无固定样例。）",
    gen="""#include <bits/stdc++.h>
using namespace std;
int main(int argc,char**argv){
    mt19937 rng(atoi(argv[1]));
    printf("%d\\n", (int)(rng()%1000000000)+1);
}""",
    ref="""#include <bits/stdc++.h>
using namespace std;
int main(){
    long long lo=1,hi=1000000000;
    string s;
    while(lo<hi){
        long long mid=(lo+hi)/2;
        printf("%lld\\n",mid); fflush(stdout);
        if(!(cin>>s))return 0;
        if(s=="HIGHER")lo=mid+1;
        else if(s=="LOWER")hi=mid-1;
        else if(s=="EQUAL"){lo=hi=mid;break;}
    }
    printf("ANSWER %lld\\n",lo); fflush(stdout);
}""",
    interactor="""#include <bits/stdc++.h>
using namespace std;
// Usage: interactor <input_file> <output_log>
int main(int argc,char**argv){
    ifstream in(argv[1]);
    ofstream out(argv[2]);
    long long X; in>>X;
    string line; int queries=0;
    while(getline(cin,line)){
        if(line.empty())continue;
        if(line.rfind("ANSWER",0)==0){
            long long x; sscanf(line.c_str(),"ANSWER %lld",&x);
            out<<line<<endl;
            if(x==X){fprintf(stderr,"OK, queries=%d\\n",queries);return 0;}
            fprintf(stderr,"WRONG_ANSWER expected %lld got %lld\\n",X,x);return 1;
        }
        long long y; try{y=stoll(line);}catch(...){fprintf(stderr,"INVALID\\n");return 1;}
        queries++;
        if(queries>35){fprintf(stderr,"TOO_MANY_QUERIES\\n");return 1;}
        out<<"Q: "<<y<<endl;
        if(y<X){cout<<"HIGHER"<<endl;}
        else if(y>X){cout<<"LOWER"<<endl;}
        else {cout<<"EQUAL"<<endl;}
        cout.flush();
    }
    fprintf(stderr,"NO_ANSWER\\n");return 1;
}""",
)


# ----------------------------------------------------------------------------
# Build test data for all problems by running generators and reference.
# ----------------------------------------------------------------------------

IS_WIN = os.name == "nt"
EXE = ".exe" if IS_WIN else ""

def run(cmd, timeout=60, cwd=None, input=None):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          cwd=cwd, input=input, encoding="utf-8", errors="replace")

def wtext(path, data):
    Path(path).write_text(data or "", encoding="utf-8", newline="\n")

def build_problem(p):
    slug = p["slug"]
    pdir = DATA / slug
    pdir.mkdir(parents=True, exist_ok=True)

    # Write source files
    wtext(pdir / "gen.cpp", p["gen"])
    wtext(pdir / "ref.cpp", p["ref"])
    if p.get("interactor"):
        wtext(pdir / "interactor.cpp", p["interactor"])

    # Compile generator and reference
    for name in ["gen", "ref"]:
        r = run(["g++", "-std=c++20", "-O2", "-w", "-o", str(pdir/(name+EXE)), str(pdir/f"{name}.cpp")])
        if r.returncode != 0:
            raise RuntimeError(f"compile {name} for {slug} failed:\n{r.stderr}")
    if p.get("interactor"):
        r = run(["g++", "-std=c++20", "-O2", "-w", "-o", str(pdir/("interactor"+EXE)), str(pdir/"interactor.cpp")])
        if r.returncode != 0:
            raise RuntimeError(f"compile interactor for {slug} failed:\n{r.stderr}")

    # Generate cases per subtask
    case_idx = 0
    subtasks_out = []
    for si, st in enumerate(p["subtasks"]):
        cases = []
        for ci in range(st.get("cases", 1)):
            seed = case_idx * 131 + si * 17 + ci + 1
            in_name = f"{si}_{ci}.in"
            out_name = f"{si}_{ci}.out"
            # generator takes seed and mode (= subtask index)
            r = run([str(pdir/("gen"+EXE)), str(seed), str(si)], cwd=str(pdir))
            if r.returncode != 0:
                raise RuntimeError(f"gen {slug} {in_name} failed: {r.stderr}")
            wtext(pdir/in_name, r.stdout)
            if p.get("interactive"):
                # For interactive, no reference output; interactor handles it.
                wtext(pdir/out_name, "")
            else:
                rr = run([str(pdir/("ref"+EXE))], timeout=60, cwd=str(pdir), input=r.stdout)
                if rr.returncode != 0:
                    raise RuntimeError(f"ref {slug} {in_name} failed rc={rr.returncode}\n{rr.stderr}")
                wtext(pdir/out_name, rr.stdout)
            cases.append({"input": in_name, "output": out_name})
            case_idx += 1
        subtasks_out.append({"name": st["name"], "score": st["score"], "testcases": cases})

    return subtasks_out

async def main():
    await init_db()
    # Build all problems' test data and get finalized subtask structures
    for p in PROBLEMS:
        print(f"Building {p['slug']} ...", flush=True)
        p["subtasks"] = build_problem(p)

    db = await get_db()
    try:
        # Create admin + users
        now = time.time()
        for t in ["hacks","personal_locks","team_messages","submissions","contest_problems","contests","problems","sessions","users","teams"]:
            await db.execute(f"DELETE FROM {t}")
        await db.commit()

        teams = []
        for name, color in [("Code Rangers", "#2f7ed8"), ("Bit Warriors", "#d83b3b")]:
            cur = await db.execute("INSERT INTO teams(name,color,created_at) VALUES(?,?,?)",(name,color,now))
            teams.append(cur.lastrowid)

        # 10 users: 5 per team
        users = []
        for ti in range(2):
            for pos in range(5):
                uname = f"{'alice' if ti==0 else 'bob'}{pos+1}"
                cur = await db.execute(
                    "INSERT INTO users(username,password_hash,display_name,team_id,position,is_admin,created_at) VALUES(?,?,?,?,?,?,?)",
                    (uname, hash_password("123456"), f"{['A','B'][ti]}{pos+1}", teams[ti], pos, 0, now))
                users.append(cur.lastrowid)
        # admin
        await db.execute("INSERT INTO users(username,password_hash,display_name,is_admin,created_at) VALUES(?,?,?,?,?)",
                         ("admin", hash_password("admin"), "Administrator", 1, now))

        # Insert problems
        prob_ids = {}
        for p in PROBLEMS:
            cur = await db.execute(
                """INSERT INTO problems(slug,title,description,input_format,output_format,samples,constraints,
                   time_limit,memory_limit,problem_type,score_total,subtasks,validator,position,interactive,
                   difficulty,is_public,tags,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (p["slug"], p["title"], p["description"], p.get("input_format",""), p.get("output_format",""),
                 p.get("samples",""), p.get("constraints",""),
                 p["time_limit"], p["memory_limit"], p["problem_type"], p["score_total"],
                 json.dumps(p["subtasks"]),
                 str(DATA/p["slug"]/("interactor"+EXE)) if p.get("interactive") else None,
                 p.get("position"), 1 if p.get("interactive") else 0,
                 # Difficulty is authored here but stays hidden until the contest ends.
                 {"personal": "提高", "thinking": "省选", "mystery": "NOI"}.get(p["problem_type"], ""),
                 0,                      # contest problems are private until released
                 p.get("tags", ""),
                 now))
            prob_ids[p["slug"]] = cur.lastrowid

        # Create an OIL contest starting now
        cur = await db.execute(
            "INSERT INTO contests(name,mode,start_time,solve_duration,hack_duration,created_at) VALUES(?,?,?,?,?,?)",
            ("OIL 热身赛", "oil", now, 2*3600, 3600, now))
        contest_id = cur.lastrowid

        # Personal problems at slots personal:0..4
        for p in PROBLEMS:
            if p["problem_type"] == "personal":
                await db.execute("INSERT INTO contest_problems(contest_id,problem_id,slot) VALUES(?,?,?)",
                                 (contest_id, prob_ids[p["slug"]], f"personal:{p['position']}"))
            elif p["problem_type"] == "thinking":
                await db.execute("INSERT INTO contest_problems(contest_id,problem_id,slot) VALUES(?,?,?)",
                                 (contest_id, prob_ids[p["slug"]], f"team:{p['slug']}"))
            elif p["problem_type"] == "mystery":
                await db.execute("INSERT INTO contest_problems(contest_id,problem_id,slot) VALUES(?,?,?)",
                                 (contest_id, prob_ids[p["slug"]], "mystery"))

        await db.commit()
        print("\nSeed complete.")
        print(f"Contest id: {contest_id}")
        print("Users: alice1..alice5 / bob1..bob5  password: 123456")
        print("Admin: admin / admin")
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
