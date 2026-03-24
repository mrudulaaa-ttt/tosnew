from __future__ import annotations

import threading
import time


def run_critical_section_demo(
    threads: int = 8,
    increments_per_thread: int = 2000,
    delay_seconds: float = 0.00001,
) -> dict[str, int]:
    """
    Demonstrates the critical section problem with and without a lock.
    Returns expected vs observed counters for both runs.
    """
    expected = threads * increments_per_thread

    shared = {"value": 0}

    def unsafe_worker() -> None:
        for _ in range(increments_per_thread):
            current = shared["value"]
            time.sleep(delay_seconds)
            shared["value"] = current + 1

    workers = [threading.Thread(target=unsafe_worker) for _ in range(threads)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    without_lock = shared["value"]

    shared = {"value": 0}
    lock = threading.Lock()

    def safe_worker() -> None:
        for _ in range(increments_per_thread):
            with lock:
                current = shared["value"]
                time.sleep(delay_seconds)
                shared["value"] = current + 1

    workers = [threading.Thread(target=safe_worker) for _ in range(threads)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    with_lock = shared["value"]

    return {
        "expected": expected,
        "without_lock": without_lock,
        "with_lock": with_lock,
        "lost_updates_without_lock": expected - without_lock,
    }
