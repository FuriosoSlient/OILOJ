#include <bits/stdc++.h>
using namespace std;
#define int long long
#define M 998244353
int dp[5010],dp2[5010][5010],flag[5010][5010];
bool check(int l,int r,int mid){
	int id=0;
	for (int i=mid; i<=r; i++){
		if (flag[i][++id]) return 0;
	}
	for (int i=l; i<mid; i++){
		if (flag[i][++id]) return 0;
	}
	return 1;
}
signed main(){
	ios::sync_with_stdio(0);
	cin.tie(0); cout.tie(0); 
	int t; cin>>t;
	while (t--){
		int n,m; cin>>n>>m;
		for (int i=1; i<=n; i++){ dp[i]=0;
			for (int j=1; j<=n; j++) dp2[i][j]=0,flag[i][j]=0;
		}
		for (int i=1; i<=m; i++){
			int x,y; cin>>x>>y;
			flag[x][y]=1;
		}
		dp[0]=1;
		for (int i=1; i<=n; i++){
			for (int j=1; j<=i; j++){
				if (check(j,i,j)){
					dp[i]+=dp[j-1];
					dp2[i][i-j+1]+=dp[j-1];
					dp[i]%=M; dp2[i][i-j+1]%=M;
				} 
				for (int k=j+1; k<=i; k++){
					if (check(j,i,k)){
						dp[i]+=(dp[j-1]-dp2[j-1][i-k+1]+M)%M;
					}
				}
			}
		}
		cout<<dp[n]<<"\n";
	}
} 
