#include<iostream>
#include<bits/stdc++.h>
using namespace std;
int mincost = INT_MAX;
int n, m, k;
void dfs(int i, vector<int>remain, int cost) {
    if (i == m + 1) {
        if (remain.size() == 0) { mincost = min(mincost, cost); }
        return;
    }
    if (cost > mincost)return;
    if (remain.size() == 0) {
        mincost = min(cost, mincost);
        return;
    }
    int mi = *min_element(remain.begin(), remain.end());
    //买陷阱
    vector<int>buy;
    int cnt = 0;
    for (int j = 0;j < remain.size();j++) {
        cnt++;
        if (remain[j] == i|| cnt % k == 0) { continue; }
        buy.push_back(remain[j]);
    }
    //不买陷阱
    vector<int>nobuy;
    for (int j = 0;j < remain.size();j++) {
        if (remain[j] == mi) { continue; }
        nobuy.push_back(remain[j]);
    }
    if (mi<=m) {
       dfs(mi+1, nobuy, cost);
     }
    if (buy.size() < remain.size()) {
      dfs(i+1, buy, cost + 1);	
     }
    }
inline void solve() {
    cin >> n >> m >> k;
    vector<int>arr(n);
    for (int i = 0;i < n;i++) {
        cin >> arr[i];
    }
    dfs(1, arr, 0);
    if (mincost == INT_MAX) {
        cout << "Zombies are on your lawn" << endl;
    }
    else {
        cout << mincost << endl;
    }
}
int T = 1;
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    while (T--) {
        solve();
    }
    return 0;
}