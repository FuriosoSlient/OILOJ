#include<bits/stdc++.h>
using namespace std;

int h,n;
struct num{
	int cnt,id;
}a[1100000];

bool cmp(num A,num B){
	return A.cnt>B.cnt;
}

int main(){
	srand(19260817);
	scanf("%d",&h);
	n=(1<<h)-1;
	for(int i=1;i<=n;i++) a[i].id=i;
	for(int i=1,x;i<=422;i++){
		int u=0,v=0,w=0;
		while(u==v||v==w||u==w){
			u=(rand()<<16|rand())%n+1;
			v=(rand()<<16|rand())%n+1;
			w=(rand()<<16|rand())%n+1;
		}
		printf("? %d %d %d\n",u,v,w);
		fflush(stdout);
		scanf("%d",&x);
		a[x].cnt++;
	}
	sort(a+1,a+n+1,cmp);
	if(h==3){
		int p1=a[1].id,p2=a[2].id,p3=a[3].id,x;
		printf("? %d %d %d\n",p1,p2,p3);
		fflush(stdout);
		scanf("%d",&x);
		if(x==p3) {printf("! %d\n",p3),fflush(stdout);return 0;}
		
		printf("? %d %d %d\n",p1,p3,p2);
		fflush(stdout);
		scanf("%d",&x);
		if(x==p2) {printf("! %d\n",p2),fflush(stdout);return 0;}
		
		printf("? %d %d %d\n",p2,p3,p1);
		fflush(stdout);
		scanf("%d",&x);
		if(x==p1) {printf("! %d\n",p1),fflush(stdout);return 0;}
	}
	
	
	int son1=a[1].id,son2=a[2].id;
	for(int i=1,x;i<=n;i++){
		if(i==son1||i==son2) continue;
		printf("? %d %d %d\n",son1,son2,i);
		fflush(stdout);
		scanf("%d",&x);
		if(x==i) {
			printf("! %d\n",x);
			fflush(stdout);
			return 0;
		}
	}
	
	return 0;
}
