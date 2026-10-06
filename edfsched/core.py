"""EDF 实时调度内核（纯标准库，行为完全确定）。

周期任务由 TaskSpec 描述：最坏执行时间 cost、周期 period、相对截止期 deadline
（省略时取周期）与释放偏移 offset。时间按整数拍推进，不使用真实时钟、线程或
网络，同一输入的输出完全一致。

对外接口：

* utilization()     —— 任务集的总利用率；
* hyperperiod()     —— 任务集的超周期；
* demand()          —— 给定长度区间内处理器需求的上界；
* is_schedulable()  —— EDF 可调度性判定；
* simulate()        —— 逐拍展开周期任务并按 EDF 调度，统计错过、抢占与空闲。
"""

from fractions import Fraction

__all__ = [
    "Job",
    "SimResult",
    "TaskSpec",
    "demand",
    "hyperperiod",
    "is_schedulable",
    "simulate",
    "utilization",
]


def _require_int(value, label):
    """确认参数是非布尔的整数。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("%s 必须是整数: %r" % (label, value))
    return value


class TaskSpec:
    """一个周期实时任务。"""

    __slots__ = ("name", "cost", "period", "deadline", "offset")

    def __init__(self, name, cost, period, deadline=None, offset=0):
        if not isinstance(name, str) or not name:
            raise ValueError("任务名必须是非空字符串")
        _require_int(cost, "最坏执行时间")
        _require_int(period, "周期")
        _require_int(offset, "释放偏移")
        if deadline is None:
            deadline = period
        else:
            _require_int(deadline, "相对截止期")
        if cost < 1:
            raise ValueError("最坏执行时间必须为正: %r" % (cost,))
        if period < 1:
            raise ValueError("周期必须为正: %r" % (period,))
        if offset < 0:
            raise ValueError("释放偏移不能为负: %r" % (offset,))
        if deadline < 1 or deadline > period:
            raise ValueError("相对截止期必须落在 1..周期 之间: %r" % (deadline,))
        self.name = name
        self.cost = cost
        self.period = period
        self.deadline = deadline
        self.offset = offset

    @property
    def implicit(self):
        """相对截止期是否恰好等于周期。"""
        return self.deadline == self.period

    def __repr__(self):
        return "TaskSpec(%s, cost=%d, period=%d, deadline=%d, offset=%d)" % (
            self.name,
            self.cost,
            self.period,
            self.deadline,
            self.offset,
        )


class Job:
    """某个任务的一次释放。"""

    __slots__ = ("task", "index", "release", "deadline", "remaining",
                 "started_at", "finished_at", "missed")

    def __init__(self, task, index, release):
        self.task = task
        self.index = index
        self.release = release
        self.deadline = release + task.deadline
        self.remaining = task.cost
        self.started_at = None
        self.finished_at = None
        self.missed = False

    def __repr__(self):
        return "Job(%s#%d, release=%d, deadline=%d, remaining=%d)" % (
            self.task.name,
            self.index,
            self.release,
            self.deadline,
            self.remaining,
        )


class SimResult:
    """一次仿真得到的执行轨迹与统计。"""

    __slots__ = ("horizon", "jobs", "trace", "misses", "busy", "idle",
                 "preemptions", "responses")

    def __init__(self, horizon, jobs, trace, misses, busy, idle,
                 preemptions, responses):
        self.horizon = horizon
        self.jobs = jobs
        self.trace = trace
        self.misses = misses
        self.busy = busy
        self.idle = idle
        self.preemptions = preemptions
        self.responses = responses

    @property
    def miss_count(self):
        """错过截止期的作业数。"""
        return len(self.misses)

    def __repr__(self):
        return "SimResult(horizon=%d, jobs=%d, misses=%d, busy=%d, idle=%d)" % (
            self.horizon,
            len(self.jobs),
            self.miss_count,
            self.busy,
            self.idle,
        )


def _spec_list(tasks):
    """检查并返回任务集。"""
    specs = list(tasks)
    for spec in specs:
        if not isinstance(spec, TaskSpec):
            raise TypeError("任务集只能包含 TaskSpec: %r" % (spec,))
    return specs


def utilization(tasks):
    """任务集的总利用率。"""
    total = 0.0
    for spec in _spec_list(tasks):
        total += spec.cost / spec.period
    return total


def hyperperiod(tasks):
    """任务集的超周期，即各周期的最小公倍数。"""
    periods = [spec.period for spec in _spec_list(tasks)]
    if not periods:
        return 1
    return max(periods)


def demand(tasks, interval):
    """截止期落在长度 interval 的区间内的作业，其执行时间的上界。"""
    if interval <= 0:
        return 0
    total = 0
    for spec in _spec_list(tasks):
        jobs = interval // spec.period
        if jobs > 0:
            total += jobs * spec.cost
    return total


def _checkpoints(specs, limit):
    """(0, limit] 内需要检查的绝对截止期，升序去重。"""
    points = set()
    for spec in specs:
        first = spec.offset + spec.deadline
        if first <= limit:
            points.add(first)
    return sorted(points)


def is_schedulable(tasks):
    """判断任务集在 EDF 下是否可调度（同步释放，相对截止期不超过周期）。"""
    specs = _spec_list(tasks)
    if not specs:
        return True
    util = utilization(specs)
    if util >= Fraction(1):
        return False
    if all(spec.implicit for spec in specs):
        return True
    limit = hyperperiod(specs)
    for point in _checkpoints(specs, limit):
        if demand(specs, point) > point:
            return False
    return True


def _release_jobs(specs, horizon):
    """把窗口内的周期释放展开成作业列表。"""
    jobs = []
    for spec in specs:
        index = 0
        release = spec.offset
        while release < horizon:
            jobs.append(Job(spec, index, release))
            index += 1
            release = spec.offset + index * spec.period
    jobs.sort(key=lambda job: job.release)
    return jobs


def _pick_next(ready):
    """挑出下一个要运行的作业，绝对截止期最早者优先。"""
    best = None
    for job in ready:
        if best is None or job.deadline < best.deadline:
            best = job
    return best


def simulate(tasks, horizon=None):
    """在给定窗口内按拍推进 EDF 调度。

    每个时刻先释放到点的作业、再淘汰已经错过截止期的作业，然后执行一个就绪
    作业一拍；没有就绪作业时该拍记为空闲。
    """
    specs = _spec_list(tasks)
    if horizon is None:
        horizon = hyperperiod(specs)
    else:
        _require_int(horizon, "仿真窗口")
        if horizon < 0:
            raise ValueError("仿真窗口不能为负: %r" % (horizon,))

    released = _release_jobs(specs, horizon)
    ready = []
    cursor = 0
    trace = []
    misses = []
    responses = {}
    busy = 0
    idle = 0
    preemptions = 0
    last = None

    for now in range(horizon):
        while cursor < len(released) and released[cursor].release <= now:
            ready.append(released[cursor])
            cursor += 1
        for job in list(ready):
            if job.remaining > 0 and job.deadline <= now:
                job.missed = True
                misses.append(job)
                ready.remove(job)
        job = _pick_next(ready)
        if job is None:
            idle += 1
            continue
        if last is not None and last is not job:
            preemptions += 1
        if job.started_at is None:
            job.started_at = now
        job.remaining -= 1
        busy += 1
        if job.remaining == 0:
            job.finished_at = now + 1
            if job.finished_at >= job.deadline:
                job.missed = True
                misses.append(job)
            else:
                responses.setdefault(job.task.name, []).append(
                    job.finished_at - job.release)
            ready.remove(job)
        trace.append({
            "time": now,
            "task": job.task.name,
            "index": job.index,
            "remaining": job.remaining,
        })
        last = job

    for job in list(ready):
        if job.remaining > 0 and job.deadline <= horizon:
            job.missed = True
            misses.append(job)

    return SimResult(horizon, released, trace, misses, busy, idle,
                     preemptions, responses)
