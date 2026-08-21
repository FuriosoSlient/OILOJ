#include<bits/stdc++.h> 
#define int long long
#define endl "\n"
using namespace std;
const int mod=998244353;
int n;
int in[100005];
void solve()
{
    cin>>n;
    for(int i=1;i<=n;i++)in[i]=0;
    for(int i=1;i<=n-1;i++)
    {
        int u,v;
        cin>>u>>v;
        in[u]++;
        in[v]++;
    }
    int res=1;
    for(int i=1;i<=n;i++)
    {
        if(in[i]%2==0)in[i]--;
        for(int j=in[i];j>=1;j-=2)res=res*j%mod;
    }
    cout<<res<<endl;
}
int T;
signed main( )
{
    cin>>T;
    while(T--)
    {
        solve();
    }
    return 0;
}