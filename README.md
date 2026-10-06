# pairwise-edfsched

一个只用 Python 标准库实现的 EDF 实时调度内核实验项目。
时间按整数拍推进，不使用真实时钟、线程或网络，同样的输入永远得到同样的输出。

## 模块内容

`edfsched/core.py` 提供：

- `TaskSpec(name, cost, period, deadline=None, offset=0)`：一个周期任务。`cost` 是最坏执行时间，
  `deadline` 是相对截止期（省略时取周期，必须落在 1..周期 之内），`offset` 是首次释放偏移。
- `utilization(tasks)`：总利用率，按精确分数比较。
- `hyperperiod(tasks)`：超周期，即各周期的最小公倍数。
- `demand(tasks, interval)`：长度 `interval` 的区间内，截止期落在其中的作业所需的处理器时间上界。
- `is_schedulable(tasks)`：EDF 可调度性判定，针对同步释放（偏移视为 0）且相对截止期不超过周期的任务集。
  利用率不超过 1 是可调度的必要条件；只要有一个任务的相对截止期小于周期，就必须再做区间需求检查。
- `simulate(tasks, horizon=None)`：把周期任务展开成作业并逐拍调度，返回 `SimResult`。

## 仿真的语义

- 每个任务的作业在 `offset + k * period`（`k = 0, 1, 2, ...`）释放，窗口内只保留释放时刻小于 `horizon` 的作业。
- 每个时刻先释放到点的作业，再把已经错过截止期且没跑完的作业记一次错过并丢弃，然后用 EDF 选一个作业跑一拍。
- EDF 的选择规则：绝对截止期最早者优先；并列时依次按任务名字典序、释放时刻、作业序号决定，顺序固定。
- 作业在等于自己绝对截止期的时刻跑完算按时完成，严格晚于截止期才算错过。没有作业可跑的那一拍记为空闲。
- `SimResult` 里的 `misses` 是错过截止期的作业，`trace` 是每个执行拍的记录，`responses` 是按时完成的
  作业的响应时间（完成时刻减去释放时刻），`preemptions` 统计上一个作业还没跑完就被别的作业换下的次数。

## 目录

```
edfsched/__init__.py   对外导出
edfsched/core.py       调度内核
tests/test_core.py     验收测试
```

## 怎么跑测试

在项目根目录执行：

```
python3 -m unittest discover -s tests -v
```

Windows 上用任意 Python 3 解释器执行同一条命令即可，例如：

```
C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe -m unittest discover -s tests -v
```
