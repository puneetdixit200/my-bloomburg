from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from internet_radar.scheduler.jobs import ScheduledJob, SmartTrigger


TRIGGER_PRIORITIES = {
    "immediate_alert": 0,
    "deep_analysis": 10,
    "crowd_alert": 20,
}

ROUTINE_PRIORITY = 100


@dataclass(frozen=True)
class QueueTask:
    priority: int
    name: str
    action: str
    topic: str = ""
    signal_id: str = ""
    job: ScheduledJob | None = None
    trigger: SmartTrigger | None = None


@dataclass(order=True)
class _QueuedItem:
    priority: int
    sequence: int
    task: QueueTask = field(compare=False)


class SchedulerPriorityQueue:
    def __init__(self) -> None:
        self._items: list[_QueuedItem] = []
        self._sequence = 0

    def push(self, task: QueueTask) -> None:
        heapq.heappush(self._items, _QueuedItem(task.priority, self._sequence, task))
        self._sequence += 1

    def pop(self) -> QueueTask:
        return heapq.heappop(self._items).task

    def drain(self) -> list[QueueTask]:
        tasks: list[QueueTask] = []
        while self._items:
            tasks.append(self.pop())
        return tasks

    def __len__(self) -> int:
        return len(self._items)


def build_priority_queue(
    triggers: list[SmartTrigger] | None = None,
    routine_jobs: list[ScheduledJob] | None = None,
) -> SchedulerPriorityQueue:
    queue = SchedulerPriorityQueue()
    for trigger in triggers or []:
        queue.push(_task_from_trigger(trigger))
    for job in routine_jobs or []:
        queue.push(_task_from_job(job))
    return queue


def _task_from_trigger(trigger: SmartTrigger) -> QueueTask:
    priority = TRIGGER_PRIORITIES.get(trigger.action, 50)
    return QueueTask(
        priority=priority,
        name=f"{trigger.action}:{trigger.signal_id}",
        action=trigger.action,
        topic=trigger.topic,
        signal_id=trigger.signal_id,
        trigger=trigger,
    )


def _task_from_job(job: ScheduledJob) -> QueueTask:
    interval_weight = job.minutes or (job.hours * 60 if job.hours else 24 * 60)
    return QueueTask(
        priority=ROUTINE_PRIORITY + interval_weight,
        name=f"routine:{job.name}",
        action="routine",
        job=job,
    )
