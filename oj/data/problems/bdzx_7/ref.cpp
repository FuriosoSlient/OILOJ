#include<bits/stdc++.h>
using namespace std;
int t,n,s,p;
int chu2(int x){return (x%2==0?x/2:x/2+1);}
int main()
{
    cin>>t;
    while(t--)
    {
        cin>>n>>s;
        while(n--) cin>>p,s=max(s,chu2(s+p));
        cout<<s<<endl;
    }
    return 0;
}