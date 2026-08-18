#include<bits/stdc++.h>
using namespace std;
const int N=3e5;
const int maxn=3e5+10;
const int mod=1e9+7;
inline int read(){
	int x=0,f=1;char c=getchar();
	while(c<'0'||c>'9'){if(c=='-')f=-1;c=getchar();}
	while(c>='0'&&c<='9'){x=(x<<1)+(x<<3)+c-'0';c=getchar();}
	return x*f;
}
int flag[maxn],mu[maxn],pri[maxn],tot;
int n,a[maxn],all,ans;
inline int gcd(int x,int y){
	if(y==0)return x;
	return gcd(y,x%y);
}
int f[6][maxn],res[maxn],flg,now[maxn];
int t1[maxn],t2[maxn];
inline void mul(int *f1,int *f2,int *f3){
	for(int i=1;i<=N;i++){
		t1[i]=t2[i]=0;
		for(int j=i;j<=N;j+=i)
			t1[i]+=f2[j],t2[i]+=f3[j];
	}
	for(int i=1;i<=N;i++){
		long long val=0;
		for(int j=1;j<=N/i;j++)
			val+=1ll*mu[j]*t1[i*j]*t2[i*j];
		f1[i]=(val!=0);
	}
}
int main(){
	mu[1]=1;
	for(int i=2;i<=N;i++){
		if(!flag[i])pri[++tot]=i,mu[i]=-1;
		for(int j=1;j<=tot&&i*pri[j]<=N;j++){
			flag[i*pri[j]]=1;
			if(i%pri[j]==0){
				mu[i*pri[j]]=0;
				break;
			}mu[i*pri[j]]=-mu[i];
		}
	}
	n=read();
	for(int i=1,x;i<=n;i++)
		x=read(),a[x]=1,all=gcd(all,x);
	if(all>1)return puts("-1")&0;
	if(a[1])return puts("1")&0;
	memcpy(f[0],a,sizeof(f[0]));
	for(int i=1;i<=5;i++)
		mul(f[i],f[i-1],f[i-1]);
	for(int i=5;~i;--i){
		if(!flg){
			if(!f[i][1]){
				memcpy(res,f[i],sizeof(res));
				flg=1;ans+=(1<<i);
			}continue;
		}mul(now,res,f[i]);
		if(!now[1]){
			memcpy(res,now,sizeof(res));
			ans+=(1<<i);
		}
	}printf("%d\n",ans+1);
	return 0;
}
