#include<bits/stdc++.h>
#define int long long
using namespace std;
const int maxn=305;
bitset<305> st[90005];
int n,a[maxn],f[90005],sum,x,y;
bool vis[maxn];
signed main(){
	scanf("%lld",&n);
	for(int i=1;i<=n;i++)scanf("%lld",&a[i]),sum+=a[i];	
	for(int i=1;i<=n;i++)
		for(int j=sum;j>=a[i];j--){
			if(f[j-a[i]]+a[i]>f[j]){
				f[j]=f[j-a[i]]+a[i];
				st[j].reset();
				st[j]|=st[j-a[i]];
				st[j].flip(i);}}
	if(f[sum/2]==sum/2&&!(sum%2)){
		cout<<"Second\n";
		cout.flush();
		scanf("%lld",&x);
		while(x){
			if(x==-1)return 0;
			if(st[sum/2][x]){
				for(int i=1;i<=n;i++)
					if(!vis[i]&&!st[sum/2][i]){
						y=i;
						cout<<i<<"\n";
						cout.flush();
						break;}}
			else{
				for(int i=1;i<=n;i++)
					if(!vis[i]&&st[sum/2][i]){
						y=i;
						cout<<i<<"\n";
						cout.flush();
						break;}}
			if(a[x]<a[y])a[y]-=a[x],a[x]=0,vis[x]=1;
			else if(a[x]==a[y])a[x]=a[y]=0,vis[x]=vis[y]=1;
			else a[x]-=a[y],a[y]=0,vis[y]=1;
			scanf("%lld",&x);}}
	else{
		cout<<"First\n";
		cout.flush();
		cout<<1<<"\n";y=1;
		cout.flush();
		scanf("%lld",&x);
		while(x){
			if(a[x]<a[y])a[y]-=a[x],a[x]=0,vis[x]=1;
			else if(a[x]==a[y])a[x]=a[y]=0,vis[x]=vis[y]=1;
			else a[x]-=a[y],a[y]=0,vis[y]=1;
			if(x==-1)return 0;
			for(int i=1;i<=n;i++)
				if(!vis[i]){
					y=i;
					cout<<i<<"\n";
					cout.flush();
					break;}
		scanf("%lld",&x);}}
	return 0;}
