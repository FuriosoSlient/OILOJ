#include <iostream>
#include<bits/stdc++.h>
using namespace std;
#include <set>
#include <algorithm>
#include <cmath>
#include <map>
#include <cstdio>
#include <string>
#include <cstring>
#include <string.h>
#include <stdlib.h>
#include <iomanip>
#include <fstream>
#include <stdio.h>
#include <stack>
#include <queue>
#include <ctype.h>
#include <vector>
#include <random>
#include<list> 
#define ll long long
#define ull unsigned long long
#define pb push_back
#define rep(i, a, n) for (int i = a; i <= n; i++)
#define per(i, a, n) for (int i = n; i >= a; i--)
#define pii pair<int, int>
#define pli pair<ll, int>
#define pil pair<int, ll>
#define pll pair<ll, ll>
#define lowbit(x) ((x)&(-x))

#define endl '\n'//交互题请删除本行
const ll inf = 1000000000000000000ll;
const int N = 2e6 + 10, M = 1e6 + 10;

///////////////////////////////////

int tt;
int n;
int num[N];
int numbeishu[N];
int maxzhi[N];
int maxmex=0;
///////////////////////////////////

bool ok(int geshu,int u)
{
    return n-num[u]>=geshu;
}

///////////////////////////////////

void init()
{
    
    rep(i,0,1000000)
    {
        if(num[i])
        {
            maxmex=i+1;
        }
        else
        {
            break;
        }
    }
}

///////////////////////////////////

int main()
{
    ios::sync_with_stdio(false);cin.tie(0);cout.tie(0);//交互题请删除本行
   // freopen("ain.txt", "r", stdin); freopen("aout.txt", "w", stdout);
    cin>>n;
    rep(i,1,n)
    {
        int temp;
        cin>>temp;
        num[temp]++;
    }
    per(i,1,1000000)
    {
        for(int j=1;i*j<=1000000;j++)
        {
            numbeishu[i]+=num[i*j];   
        }
    }
    int cnt=0;
    per(i,1,1000000)
    {
        if(numbeishu[i]>cnt)
        {
            rep(j,cnt+1,numbeishu[i])
            {
                maxzhi[j]=i;
            }
            cnt=numbeishu[i];
        }
    }
    init();
    rep(i,1,n)
    {
        if(n==num[0])
        {
            cout<<1<<" ";
            continue;
        }
        int ans=0;
        //mex=0
        if(n-num[0]>=i)
        {
            ans=maxzhi[i];
        }
        //mex=1
        if(i>=2&&num[0]&&n-num[1]>=i)
        {
            int num0=min(i-1,num[0]);
            int shengyu=i-num0;
            ans=max(ans,(1^maxzhi[shengyu]));
            if(maxzhi[shengyu]>1&&numbeishu[  maxzhi[shengyu]-1     ]>=shengyu)
            {
                ans=max(ans,(1^(maxzhi[shengyu]-1   )  ));
            }
        }
        //mex>=2
        if(i>=2&&num[0]&&num[1])
        {
            int lilun=min(i,maxmex);
            if(ok(i,lilun))
            {
                ans=max(ans,(lilun^1));
            }
            lilun--;
            if(ok(i,lilun))
            {
                ans=max(ans,(lilun^1));
            }
        }
        cout<<ans<<" ";
    }
    return 0;
}