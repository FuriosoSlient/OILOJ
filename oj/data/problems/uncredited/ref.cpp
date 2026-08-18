//problem:B
#include <bits/stdc++.h>
using namespace std;

#define pb push_back
#define mk make_pair
#define lob lower_bound
#define upb upper_bound
#define fi first
#define se second
#define SZ(x) ((int)(x).size())

typedef unsigned int uint;
typedef long long ll;
typedef unsigned long long ull;
typedef pair<int,int> pii;

const int MOD=1e9+7;
inline int mod1(int x){return x<MOD?x:x-MOD;}
inline int mod2(int x){return x<0?x+MOD:x;}
inline void add(int& x,int y){x=mod1(x+y);}
inline void sub(int& x,int y){x=mod2(x-y);}
inline int pow_mod(int x,int i){int y=1;while(i){if(i&1)y=(ll)y*x%MOD;x=(ll)x*x%MOD;i>>=1;}return y;}

const int MAXN=1e6;
int n,p,a[MAXN+5];

int main() {
	int T;cin>>T;while(T--){
		cin>>n>>p;
		map<int,int>mp;
		for(int i=1;i<=n;++i){
			cin>>a[i];
			mp[-a[i]]++;
		}
		if(p==1){
			cout<<(n&1)<<endl;
			continue;
		}
		int summx=0,summn=0;
		bool flag=0;
		for(map<int,int>::iterator it=mp.begin();it!=mp.end();++it){
			int k=-(it->fi);
			int cnt=(it->se);
			//cout<<k<<" "<<cnt<<endl;
			int v=pow_mod(p,k);
			if(flag){
				add(summn,(ll)v*cnt%MOD);
				continue;
			}
			if(cnt&1){
				ll need=1;
				for(int kk=k-1;kk>=0;--kk){
					need*=p;
					if(need>MAXN)break;
					if(!mp.count(-kk))continue;
					if(mp[-kk]>=need){
						need=0;
						break;
					}
					need-=mp[-kk];
				}
				if(!need){
					need=1;
					for(int kk=k-1;kk>=0;--kk){
						need*=p;
						if(need>MAXN)break;
						if(!mp.count(-kk))continue;
						if(mp[-kk]>=need){
							mp[-kk]-=need;
							need=0;
							break;
						}
						need-=mp[-kk];
						mp[-kk]=0;
					}
					add(summx,(ll)v*(cnt/2+1)%MOD);
					add(summn,(ll)v*(cnt/2+1)%MOD);
				}
				else{
					flag=1;
					add(summx,(ll)v*(cnt/2+1)%MOD);
					add(summn,(ll)v*(cnt/2)%MOD);
				}
			}
			else{
				add(summx,(ll)v*(cnt/2)%MOD);
				add(summn,(ll)v*(cnt/2)%MOD);
			}
		}
		cout<<mod2(summx-summn)<<endl;
	}
	return 0;
}
