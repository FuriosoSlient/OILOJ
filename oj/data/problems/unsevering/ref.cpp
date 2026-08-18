#pragma GCC optimize("O3")
#include<bits/stdc++.h>
using namespace std;
#define ffor(i,j,k) for(int i=(j);i<=(k);i++)
#define rfor(i,j,k) for(int i=(k);i>=(j);i--)
#define ll long long
#define ull unsigned ll
#define pii pair<int,int>
#define pll pair<ll,ll>
#define umap unordered_map 
#define pq priority_queue
#define pb push_back
#define pf push_front
#define pob pop_back 
#define pof pop_front
#define vec vector 
#define sta stack 
#define que queue 
#define deq deque
#define fi first 
#define se second
#define fr front 
#define ba back
#define __ " "
#define gc getchar
#define file(x) freopen(x".in", "r", stdin), freopen(x".out", "w", stdout)
template<typename T>
void read(T &x){
    x=0;ll f=1;char c=gc();
    while(!isdigit(c)){
        if(c == '-'){
            f = -f;
        }
        c=gc();
    }while(isdigit(c)){
        x = x*10 + c - '0';
        c=gc();
    }
    x*=f;
}
template<typename T,typename ...A>
void read(T &x,A &...t){
    read(x);read(t...);
}
const int Mod = 998244353;
const int N = 2e5+5;
struct Ed{int to;ll a,b;__int128 w;};
int n;
vec<vec<Ed>> e;
vec<ll> sz;
__int128 S,mps;
__int128 dp[N];
void dfs1(int u,int p){
    sz[u] = 1;
    for(auto &ed:e[u]){
        int v = ed.to;
        if(v == p) continue;
        dfs1(v,u);
        sz[u] += sz[v];
        __int128 ce = (__int128)2*sz[v]*(n-sz[v]);
        S += ce*ed.a;
        ed.w = ed.b - ce*ed.a;
    }
}
void dfs2(int u,int p){
    dp[u] = 0;
    __int128 bd = 0;
    for(auto &ed:e[u]){
        int v = ed.to;
        if(v == p) continue;
        dfs2(v,u);
        __int128 val = dp[v] + ed.w;
        if(mps > bd + val) mps = bd + val;
        if(bd > val) bd = val;
    }
    dp[u] = bd;
}
void solve(){
    cin>>n;
    e.assign(n+1,vec<Ed>());
    sz.assign(n+1,0);
    ffor(i,1,n-1){
        int u,v;ll a,b;
        cin>>u>>v>>a>>b;
        e[u].pb({v,a,b,0});
        e[v].pb({u,a,b,0});
    }
    S = 0;
    mps = (__int128)1 << 120;
    dfs1(1,0);
    dfs2(1,0);
    __int128 tc = S + mps;
    ll ans = (ll)(tc % Mod);
    if(ans < 0) ans += Mod;
    cout<<ans<<'\n';
}
int main(){
    ios::sync_with_stdio(0);cin.tie(0);
    int T=1;
    cin>>T;
    while(T--){
        solve();
    }
    return 0;
}