#include "testlib.h"
#include <cmath>

// 特殊评测 (SPJ) —— 使用 testlib 编写
// 调用约定: spj <input> <output> <answer>
//   inf  = 选手看到的输入      ouf = 选手的输出      ans = 标准答案
// 判定结果通过 quitf 返回:
//   quitf(_ok,  "...")  通过
//   quitf(_wa,  "...")  答案错误
//   quitf(_pe,  "...")  格式错误
// 下面是一个「允许 1e-6 误差的实数比较」示例，请按题目需要修改。

int main(int argc, char* argv[]) {
    registerTestlibCmd(argc, argv);

    double ja = ans.readDouble();
    double pa = ouf.readDouble();

    if (std::fabs(ja - pa) <= 1e-6) {
        quitf(_ok, "answer is correct: %.10f", pa);
    } else {
        quitf(_wa, "expected %.10f, found %.10f", ja, pa);
    }
}
