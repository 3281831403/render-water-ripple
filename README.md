# render-water-ripple

## 题面

换成程序化水面后，波浪朝各方向速度不同、接缝处还有拉伸：相位用 `freq*time` 但方向未归一，波速随方向变化；高度不乘振幅，波形固定；法线用有限差分但步长过大，细节丢失；法线不归一，反射过亮；折射偏移不 wrap，边缘出现拉伸；菲涅尔用常数，视线角度无关；波合并不归一，总振幅溢出；UV 循环用 clamp，接缝明显；批量共用波状态，帧之间串；`amp<0` 不校验，波形反相。`water/ripple.py` 是核心，`tests/test_ripple.py` 15个红。要修的是：实现 8 个函数并消除上述 10 个缺陷，同时遵守 UV 0..1、波数、振幅与 1e-6 容差的契约，让全部 15 个测试通过。

## 运行方式

在仓库根目录运行：

```console
python -m pytest tests -q
```

初始状态下应恰好得到 `15 failed`，且不能出现 collection、import 或 syntax error。修复时只修改 `water/ripple.py`；`tests/test_ripple.py` 不可修改。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 图形渲染 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

- 仅使用标准库（`math`）与 pytest。
- 离线运行，不使用随机数，不访问网络。
- 波的数据结构统一为 `{"dir", "freq", "amp", "speed"}`。
- `tests/test_ripple.py` 不可修改；所有修复都在 `water/ripple.py` 中完成。
