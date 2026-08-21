#include<bits/stdc++.h>
#define fi first
#define se second
#define mk make_pair
#define pii pair<int,int> 
#define int long long
#define mod 998244353
#define inv2 499122177
using namespace std;
int n,q,u,v,cc,pw[105],t[82000000][2],f[82000000];
bool vis[82000000]; vector<pii> vec;
int dfs(int p)
{
    if(vis[p]) return f[p]; vis[p]=1;
    int ls=(t[p][0]?2*dfs(t[p][0]):0),rs=(t[p][1]?2*dfs(t[p][1])+1:0);
    return f[p]=(t[p][0]&&t[p][1]?(ls+rs)%mod*inv2%mod:(ls+rs)%mod);
}
void psh(int l,int r,int b)
{
    if((l&((1ull<<b)-1))==0&&((r&((1ull<<b)-1))==((1ull<<b)-1)))
    {
        vec.push_back(mk(b,l>>b));
        return;
    }
    if(((l>>(b-1))&1)==((r>>(b-1))&1)){psh(l,r,b-1);return;}
    psh(l,l|((1ull<<(b-1))-1),b-1);
    psh((r>>(b-1))<<(b-1),r,b-1);
}
signed main()
{
    cin>>n,pw[0]=1; for(int i=1;i<=100;i++) pw[i]=pw[i-1]*2%mod;
    for(int i=1;i<=n;i++) cin>>u>>v,psh(u,v,63);
    sort(vec.begin(),vec.end(),greater<>());
    for(int i=1;i<=vec[0].fi;i++)
        t[i][0]=t[i][1]=i+1;
    cc=vec[0].fi+1;int sizz=vec.size();
    for(int i=0;i<sizz;i++)
    {
        int b=vec[i].fi,l=vec[i].se,p=1;
        for(int i=1;i<=b;i++) p=t[p][0];
        for(int i=1;i<=63-b;i++,l/=2)
        {
            t[++cc][0]=t[t[p][l&1]][0];
            t[cc][1]=t[t[p][l&1]][1];
            t[p][l&1]=cc,p=t[p][l&1];
        }
    } dfs(1);
    cin>>q;
    while(q--)
    {
        cin>>u; int p=1,C=0;
        for(int i=u;i;i/=2) p=t[p][i%2],C++;
        cout<<(f[p]*pw[C]%mod+u)%mod<<endl;
    }
    return 0;
}