"""EDF 实时调度内核：可调度性判定、区间需求与逐拍仿真。"""

from .core import (
    Job,
    SimResult,
    TaskSpec,
    demand,
    hyperperiod,
    is_schedulable,
    simulate,
    utilization,
)

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
