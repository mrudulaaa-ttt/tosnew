from __future__ import annotations

from process.process import Process


class Scheduler:
    """Ticketing OS scheduler constrained to FCFS for fairness and predictability."""

    def __init__(self, algorithm: str = "FCFS", time_quantum: float = 0.03) -> None:
        chosen = algorithm.upper()
        if chosen != "FCFS":
            raise ValueError("Only FCFS scheduling is enabled for this ticketing OS.")
        self.algorithm = "FCFS"
        self.time_quantum = time_quantum

    def set_algorithm(self, algorithm: str) -> None:
        if algorithm.upper() != "FCFS":
            raise ValueError("Only FCFS scheduling is enabled for this ticketing OS.")
        self.algorithm = "FCFS"

    def pick_next(self, ready_processes: list[Process]) -> Process | None:
        if not ready_processes:
            return None
        return min(ready_processes, key=lambda p: p.pcb.arrival_time)
