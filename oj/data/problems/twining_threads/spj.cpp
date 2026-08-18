#include "testlib.h"
#include <iostream>
#include <vector>
#include <string>
#include <bitset>
#include <algorithm>

using namespace std;

int main(int argc, char* argv[]) {
    // 注册交互器
    registerInteraction(argc, argv);

    // 从标准输入读入测试数据
    int n = inf.readInt();
    vector<int> a(n);
    int total_sum = 0;
    for (int i = 0; i < n; i++) {
        a[i] = inf.readInt();
        total_sum += a[i];
    }

    // 将初始状态输出给选手的标准输入
    cout << n << endl;
    for (int i = 0; i < n; i++) {
        cout << a[i] << (i == n - 1 ? "" : " ");
    }
    cout << endl;
    cout.flush();

    bool can_part = false;
    vector<int> set_id(n, 1);

    // 0-1 背包 DP 判断是否可以分成两个和相等的子集
    if (total_sum % 2 == 0) {
        int target = total_sum / 2;
        // 使用位图优化，最大极限 45005 轻松满足
        vector<bitset<45005>> dp(n + 1);
        dp[0][0] = 1;
        for (int i = 0; i < n; i++) {
            dp[i + 1] = dp[i] | (dp[i] << a[i]);
        }
        
        if (dp[n][target]) {
            can_part = true;
            // 回溯找到其中一个子集
            int curr = target;
            for (int i = n - 1; i >= 0; i--) {
                if (curr >= a[i] && dp[i][curr - a[i]]) {
                    set_id[i] = 0; // 划分至子集 0
                    curr -= a[i];
                }
            }
        }
    }

    // 获取选手的阵营选择
    string role = ouf.readToken();
    if (role != "First" && role != "Second") {
        quitf(_wa, "Expected First or Second, but found %s", role.c_str());
    }

    // ============================================
    // 选手选择 First（评测机执 Second）
    // ============================================
    if (role == "First") {
        while (true) {
            int i = ouf.readInt();
            if (i == -1) {
                quitf(_wa, "Contestant made an invalid move and printed -1");
            }
            if (i == 0) {
                quitf(_wa, "Contestant printed 0 but game is not over");
            }

            i--; // 1-based 转 0-based
            if (i < 0 || i >= n || a[i] == 0) {
                cout << -1 << endl; // 通知选手违规
                cout.flush();
                quitf(_wa, "Invalid index chosen by contestant: %d", i + 1);
            }

            int j = -1;
            if (can_part) {
                // 如果是评测机必胜状态，维护集合平衡
                for (int k = 0; k < n; k++) {
                    if (k != i && a[k] > 0 && set_id[k] != set_id[i]) {
                        j = k;
                        break;
                    }
                }
                // Fallback（逻辑上不可达，以防万一）
                if (j == -1) { 
                    for (int k = 0; k < n; k++) {
                        if (k != i && a[k] > 0) { j = k; break; }
                    }
                }
            } else {
                // 如果是评测机必败状态，任选一个可用元素回应即可
                for (int k = 0; k < n; k++) {
                    if (k != i && a[k] > 0) {
                        j = k;
                        break;
                    }
                }
            }

            if (j == -1) { // 评测机穷途末路，选手获胜
                cout << 0 << endl;
                cout.flush();
                quitf(_ok, "Contestant wins");
            }

            cout << j + 1 << endl;
            cout.flush();
            
            int d = min(a[i], a[j]);
            a[i] -= d;
            a[j] -= d;

            // 如果这一轮过后没有非零元素了，则宣告选手(第一玩家)无法再移动，判决选手败。
            bool has_pos = false;
            for (int x : a) {
                if (x > 0) has_pos = true;
            }
            if (!has_pos) {
                quitf(_wa, "Contestant (First) has no moves left");
            }
        }
    } 
    // ============================================
    // 选手选择 Second（评测机执 First）
    // ============================================
    else {
        while (true) {
            int i = -1;
            // First 只需每次贪心/任选一个正元素即可维系必胜局。
            for (int k = 0; k < n; k++) {
                if (a[k] > 0) {
                    i = k;
                    break;
                }
            }

            if (i == -1) {
                cout << 0 << endl;
                cout.flush();
                quitf(_ok, "Contestant wins");
            }

            cout << i + 1 << endl;
            cout.flush();

            // 预判选手作为 Second 是否还有路可走
            bool has_j = false;
            for (int k = 0; k < n; k++) {
                if (k != i && a[k] > 0) has_j = true;
            }
            if (!has_j) { // 除 i 以外已无正元素，Second 面临死局
                quitf(_wa, "Contestant (Second) has no moves left");
            }

            int j = ouf.readInt();
            if (j == -1) {
                quitf(_wa, "Contestant made an invalid move and printed -1");
            }
            if (j == 0) {
                quitf(_wa, "Contestant printed 0 but First still had moves");
            }

            j--;
            if (j < 0 || j >= n || j == i || a[j] == 0) {
                cout << -1 << endl;
                cout.flush();
                quitf(_wa, "Invalid index chosen by contestant: %d", j + 1);
            }

            int d = min(a[i], a[j]);
            a[i] -= d;
            a[j] -= d;
        }
    }

    return 0;
}