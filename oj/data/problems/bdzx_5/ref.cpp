#include<bits/stdc++.h>
using namespace std;
int t,n,a[2000005],c[2000005];bool flg[1<<20],hav[2000005];
int main()
{
    ios::sync_with_stdio(false);
    cin.tie(0),cout.tie(0);
    for(int i=1;i<=20;i++) flg[(1<<i)-1]=1;
    cin>>t;
    while(t--)
    {
        cin>>n; int cc=0,f=1;
        for(int i=1;i<=n;i++) cin>>a[i],c[a[i]]++,hav[a[i]]=1;
        for(int i=1;i<n;i++) cc+=(a[i]!=a[i+1]);
        for(int i=1;i<=n;i++)
        {
            f&=flg[c[a[i]]];
            if(hav[a[i]]) cc--,hav[a[i]]=0;
        } if(f&&cc==-1) cout<<"Yes\n"; else cout<<"No\n";
        for(int i=1;i<=n;i++) c[i]=0;
    }
    return 0;
}