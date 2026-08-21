#include<bits/stdc++.h>
#define int long long
using namespace std;
int t,l,r;
int sqz(int x,int y){return (x%y==0?x/y:x/y+1);}
signed main()
{
    cin>>t;
    while(t--)
    {
        cin>>l>>r;
        if(l==r){cout<<(l==1?"0":"infty")<<endl;continue;}
        int num=sqz(l-1,r-l),shou=l-1,mo=(l-1+(num-1)*(l-r));
        assert(mo>=0);
        cout<<(shou+mo)*num/2<<endl;
    }
    return 0;
}