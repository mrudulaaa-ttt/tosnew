from __future__ import annotations

import json
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from kernel import Kernel
from process.process import ProcessState
from syscalls import sys_create_process, sys_log_event, sys_request_seat

FCFS_ONLY = "FCFS"
ZONE_PRICING = {
    "Platinum": 620,
    "Gold": 390,
    "Silver": 240,
}
ZONE_TO_KERNEL_CATEGORY = {
    "Platinum": "VIP",
    "Gold": "Gold",
    "Silver": "Silver",
}
ROW_LAYOUT = [
    {"row": "A", "zone": "Platinum", "count": 12, "aisles": {4, 8}},
    {"row": "B", "zone": "Platinum", "count": 12, "aisles": {4, 8}},
    {"row": "C", "zone": "Platinum", "count": 12, "aisles": {4, 8}},
    {"row": "D", "zone": "Gold", "count": 14, "aisles": {5, 10}},
    {"row": "E", "zone": "Gold", "count": 14, "aisles": {5, 10}},
    {"row": "F", "zone": "Gold", "count": 14, "aisles": {5, 10}},
    {"row": "G", "zone": "Silver", "count": 16, "aisles": {6, 12}},
    {"row": "H", "zone": "Silver", "count": 16, "aisles": {6, 12}},
    {"row": "J", "zone": "Silver", "count": 16, "aisles": {6, 12}},
]
EVENT_TEMPLATES = [
    {
        "event_id": "evt-red-room",
        "title": "Red Room Rewind",
        "subtitle": "Retro pop concert",
        "about": "A synth-heavy live set with a crowd-pleasing encore and a full brass section.",
        "venue": "Phoenix Arena",
        "duration": "2h 10m",
        "language": "English",
        "format": "Live Concert",
        "badge": "Hot",
        "theme": "ruby",
        "shows": [
            {
                "show_id": "show-red-room-730",
                "label": "7:30 PM",
                "date_label": "Fri 19 Mar",
                "auditorium": "Arena Deck A",
                "experience": "Doors open 45 mins before showtime",
                "preset_sold": ["A1", "A2", "B5", "B6", "D3", "E7", "G8", "H9"],
            },
            {
                "show_id": "show-red-room-930",
                "label": "9:30 PM",
                "date_label": "Fri 19 Mar",
                "auditorium": "Arena Deck A",
                "experience": "Late night encore edition",
                "preset_sold": ["A4", "C8", "D7", "E8", "F11", "G5"],
            },
        ],
    },
    {
        "event_id": "evt-laugh-club",
        "title": "Saturday Laugh Club",
        "subtitle": "Stand-up special",
        "about": "Sharp crowd work, two openers, and a tight ninety-minute headline set.",
        "venue": "Studio 9 Comedy Hub",
        "duration": "1h 35m",
        "language": "English, Hindi",
        "format": "Stand-up Comedy",
        "badge": "Fast Filling",
        "theme": "midnight",
        "shows": [
            {
                "show_id": "show-laugh-club-630",
                "label": "6:30 PM",
                "date_label": "Sat 20 Mar",
                "auditorium": "Black Box 2",
                "experience": "Intimate room, no interval",
                "preset_sold": ["A3", "A4", "B3", "B4", "C6", "D9", "G12"],
            },
            {
                "show_id": "show-laugh-club-845",
                "label": "8:45 PM",
                "date_label": "Sat 20 Mar",
                "auditorium": "Black Box 2",
                "experience": "Prime crowd-work slot",
                "preset_sold": ["A7", "A8", "C4", "D5", "E6", "F7", "J10"],
            },
        ],
    },
    {
        "event_id": "evt-stage-whispers",
        "title": "Stage Whispers",
        "subtitle": "Contemporary theatre",
        "about": "An intimate chamber drama with a cinematic score and a minimalist stage design.",
        "venue": "Civic Playhouse",
        "duration": "2h 00m",
        "language": "English",
        "format": "Theatre",
        "badge": "Editors Pick",
        "theme": "amber",
        "shows": [
            {
                "show_id": "show-stage-whispers-500",
                "label": "5:00 PM",
                "date_label": "Sun 21 Mar",
                "auditorium": "Main Stage",
                "experience": "Front rows recommended for best sight lines",
                "preset_sold": ["A9", "A10", "B2", "C5", "D8", "H6"],
            },
            {
                "show_id": "show-stage-whispers-800",
                "label": "8:00 PM",
                "date_label": "Sun 21 Mar",
                "auditorium": "Main Stage",
                "experience": "Evening house with interval service",
                "preset_sold": ["A5", "B5", "B6", "E4", "F4", "G11", "J14"],
            },
        ],
    },
]


@dataclass(slots=True)
class SeatState:
    seat_id: str
    row_label: str
    number: int
    zone: str
    price: int
    status: str = "available"
    order_id: str | None = None
    pid: int | None = None


@dataclass(slots=True)
class ShowState:
    show_id: str
    event_id: str
    label: str
    date_label: str
    auditorium: str
    experience: str
    seats: dict[str, SeatState]
    row_layout: list[dict[str, Any]]
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


@dataclass(slots=True)
class BookingOrder:
    order_id: str
    customer_name: str
    email: str
    event_id: str
    show_id: str
    requested_seats: list[str]
    created_at: float
    pids: list[int] = field(default_factory=list)


class TicketingPlatform:
    def __init__(self) -> None:
        self.kernel = Kernel(scheduler_algorithm=FCFS_ONLY)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._orders: dict[str, BookingOrder] = {}
        self._pid_to_order: dict[int, str] = {}
        self._pid_to_seat_ref: dict[int, tuple[str, str, str]] = {}
        self._order_sequence = 1
        self._events, self._shows = self._build_catalog()
        self._parallel_metrics = {"mean_of_means": 0.0, "workers": 0.0}
        self._scheduler_thread: threading.Thread | None = None
        self._pulse_thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._configure_kernel_inventory()
        try:
            self._parallel_metrics = self.kernel.run_parallel_metrics()
        except Exception as exc:
            self.kernel.file_manager.log(f"parallel_metrics_unavailable: {exc}")

        self.kernel.boot()
        sys_log_event(
            self.kernel,
            "boot_complete",
            details={"scheduler": FCFS_ONLY, "mode": "bookmyshow_like_ui"},
            caller_role="kernel",
        )
        sys_log_event(
            self.kernel,
            "storefront_opened",
            details={"events": len(self._events), "shows": len(self._shows)},
            caller_role="kernel",
        )
        self._drain_events()

        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="tos-ui-scheduler",
        )
        self._pulse_thread = threading.Thread(
            target=self._pulse_loop,
            daemon=True,
            name="tos-ui-seat-sync",
        )
        self._scheduler_thread.start()
        self._pulse_thread.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        if self._scheduler_thread is not None:
            self._scheduler_thread.join(timeout=2)
        if self._pulse_thread is not None:
            self._pulse_thread.join(timeout=2)
        self._drain_events()
        self.kernel.shutdown()
        self._started = False

    def get_dashboard(self, event_id: str | None = None, show_id: str | None = None) -> dict[str, Any]:
        self._sync_runtime_state()
        selected_event = self._resolve_event(event_id)
        selected_show = self._resolve_show(selected_event["event_id"], show_id)
        return {
            "events": self._build_event_cards(selected_event["event_id"]),
            "selected_event": self._build_selected_event_view(selected_event, selected_show.show_id),
            "selected_show": self._build_show_view(selected_show),
            "recent_bookings": self._build_recent_bookings(),
            "meta": {
                "updated_at": time.time(),
                "workers": int(self._parallel_metrics.get("workers", 0)),
                "load_sample": round(float(self._parallel_metrics.get("mean_of_means", 0.0)), 2),
            },
        }

    def create_order(
        self,
        customer_name: str,
        email: str,
        event_id: str,
        show_id: str,
        seat_ids: list[str],
    ) -> dict[str, Any]:
        customer = customer_name.strip()
        email_value = email.strip()
        selected_seats = self._sort_seat_ids(seat_ids)
        if not customer:
            raise ValueError("Please enter the booker name.")
        if "@" not in email_value or email_value.startswith("@") or email_value.endswith("@"):
            raise ValueError("Please enter a valid email address.")
        if not selected_seats:
            raise ValueError("Select at least one seat before continuing.")
        if len(selected_seats) > 8:
            raise ValueError("You can book up to 8 seats in one order.")

        event = self._events.get(event_id)
        if event is None:
            raise ValueError("That event is no longer available.")
        show = self._shows.get(show_id)
        if show is None or show.event_id != event_id:
            raise ValueError("That show is no longer available.")

        with self._lock:
            order_id = f"BMS-{self._order_sequence:04d}"
            self._order_sequence += 1
            order = BookingOrder(
                order_id=order_id,
                customer_name=customer,
                email=email_value,
                event_id=event_id,
                show_id=show_id,
                requested_seats=selected_seats,
                created_at=time.time(),
            )
            self._orders[order_id] = order

        unavailable_seats: list[str] = []
        for seat_id in selected_seats:
            seat = show.seats.get(seat_id)
            if seat is None:
                unavailable_seats.append(seat_id)
                continue
            with show.lock:
                if seat.status != "available":
                    unavailable_seats.append(seat_id)
                    continue
                seat.status = "processing"
                seat.order_id = order_id
                seat.pid = None

            pid = sys_create_process(
                self.kernel,
                ZONE_TO_KERNEL_CATEGORY[seat.zone],
                self._derive_priority(seat.zone),
                self._derive_burst_time(seat.zone),
                self._derive_pages(seat.zone),
                caller_role="user",
            )
            sys_request_seat(self.kernel, pid, ZONE_TO_KERNEL_CATEGORY[seat.zone], caller_role="user")
            order.pids.append(pid)
            with show.lock:
                seat.pid = pid
            with self._lock:
                self._pid_to_order[pid] = order_id
                self._pid_to_seat_ref[pid] = (show_id, seat_id, order_id)

        if unavailable_seats:
            sys_log_event(
                self.kernel,
                "seat_conflict",
                details={
                    "order_id": order_id,
                    "show_id": show_id,
                    "seats": unavailable_seats,
                },
                caller_role="user",
            )

        sys_log_event(
            self.kernel,
            "booking_submitted",
            details={
                "order_id": order_id,
                "event_id": event_id,
                "show_id": show_id,
                "seats": selected_seats,
            },
            caller_role="user",
        )
        self._drain_events()
        self._wait_for_settlement(order.pids, timeout_seconds=0.9)
        self._sync_runtime_state()
        return self.get_order(order_id)

    def get_order(self, order_id: str) -> dict[str, Any]:
        self._sync_runtime_state()
        order = self._orders.get(order_id)
        if order is None:
            raise KeyError(f"Unknown order id: {order_id}")
        return self._build_order_view(order)

    def _build_catalog(self) -> tuple[dict[str, dict[str, Any]], dict[str, ShowState]]:
        events: dict[str, dict[str, Any]] = {}
        shows: dict[str, ShowState] = {}
        for template in EVENT_TEMPLATES:
            event = {
                "event_id": template["event_id"],
                "title": template["title"],
                "subtitle": template["subtitle"],
                "about": template["about"],
                "venue": template["venue"],
                "duration": template["duration"],
                "language": template["language"],
                "format": template["format"],
                "badge": template["badge"],
                "theme": template["theme"],
                "show_ids": [],
            }
            for show_meta in template["shows"]:
                show = self._build_show(template["event_id"], show_meta)
                event["show_ids"].append(show.show_id)
                shows[show.show_id] = show
            events[event["event_id"]] = event
        return events, shows

    def _build_show(self, event_id: str, show_meta: dict[str, Any]) -> ShowState:
        sold_set = set(show_meta.get("preset_sold", []))
        seats: dict[str, SeatState] = {}
        for row_def in ROW_LAYOUT:
            for number in range(1, row_def["count"] + 1):
                seat_id = f"{row_def['row']}{number}"
                seats[seat_id] = SeatState(
                    seat_id=seat_id,
                    row_label=row_def["row"],
                    number=number,
                    zone=row_def["zone"],
                    price=ZONE_PRICING[row_def["zone"]],
                    status="sold" if seat_id in sold_set else "available",
                )
        return ShowState(
            show_id=show_meta["show_id"],
            event_id=event_id,
            label=show_meta["label"],
            date_label=show_meta["date_label"],
            auditorium=show_meta["auditorium"],
            experience=show_meta["experience"],
            seats=seats,
            row_layout=[dict(row_def) for row_def in ROW_LAYOUT],
        )

    def _configure_kernel_inventory(self) -> None:
        available = Counter({"VIP": 0, "Gold": 0, "Silver": 0})
        for show in self._shows.values():
            for seat in show.seats.values():
                if seat.status == "available":
                    available[ZONE_TO_KERNEL_CATEGORY[seat.zone]] += 1
        seat_manager = self.kernel.seat_manager
        with seat_manager._lock:
            seat_manager._seats = dict(available)
            seat_manager._allocations.clear()
            seat_manager._semaphores = {
                category: threading.Semaphore(count)
                for category, count in seat_manager._seats.items()
            }
        self.kernel.storage.save_seats(seat_manager.available())

    def _sync_runtime_state(self) -> None:
        process_snapshot = self.kernel.process_manager.snapshot()
        process_map = {int(proc["pid"]): proc for proc in process_snapshot["processes"]}
        bookings = self.kernel.storage.load_bookings()
        booked_pids = {
            int(entry["process_id"])
            for entry in bookings
            if entry.get("process_id") is not None
        }

        with self._lock:
            refs = dict(self._pid_to_seat_ref)

        for pid, (show_id, seat_id, order_id) in refs.items():
            show = self._shows.get(show_id)
            if show is None:
                continue
            seat = show.seats.get(seat_id)
            if seat is None:
                continue
            process = process_map.get(pid)
            with show.lock:
                if pid in booked_pids:
                    seat.status = "sold"
                    seat.order_id = order_id
                    seat.pid = pid
                elif process and process["state"] == ProcessState.WAITING.value:
                    if seat.order_id == order_id and seat.status == "processing":
                        seat.status = "available"
                        seat.order_id = None
                        seat.pid = None
                elif process and process["state"] == ProcessState.TERMINATED.value and pid not in booked_pids:
                    if seat.order_id == order_id and seat.status == "processing":
                        seat.status = "available"
                        seat.order_id = None
                        seat.pid = None

    def _wait_for_settlement(self, pids: list[int], timeout_seconds: float) -> None:
        if not pids:
            return
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            self._sync_runtime_state()
            process_snapshot = self.kernel.process_manager.snapshot()
            process_map = {int(proc["pid"]): proc for proc in process_snapshot["processes"]}
            bookings = self.kernel.storage.load_bookings()
            booked_pids = {
                int(entry["process_id"])
                for entry in bookings
                if entry.get("process_id") is not None
            }
            if all(
                pid in booked_pids
                or process_map.get(pid, {}).get("state") in {ProcessState.WAITING.value, ProcessState.TERMINATED.value}
                for pid in pids
            ):
                return
            time.sleep(0.05)

    def _build_event_cards(self, selected_event_id: str) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for event in self._events.values():
            available_counts = [self._show_available_count(self._shows[show_id]) for show_id in event["show_ids"]]
            cards.append(
                {
                    "event_id": event["event_id"],
                    "title": event["title"],
                    "subtitle": event["subtitle"],
                    "venue": event["venue"],
                    "badge": event["badge"],
                    "theme": event["theme"],
                    "language": event["language"],
                    "format": event["format"],
                    "starting_price_label": f"Rs. {min(ZONE_PRICING.values()):,} onwards",
                    "available_label": f"{sum(available_counts)} seats across {len(event['show_ids'])} shows",
                    "selected": event["event_id"] == selected_event_id,
                }
            )
        return cards

    def _build_selected_event_view(self, event: dict[str, Any], selected_show_id: str) -> dict[str, Any]:
        shows = [
            self._build_show_chip(self._shows[show_id], selected_show_id)
            for show_id in event["show_ids"]
        ]
        return {
            "event_id": event["event_id"],
            "title": event["title"],
            "subtitle": event["subtitle"],
            "about": event["about"],
            "venue": event["venue"],
            "duration": event["duration"],
            "language": event["language"],
            "format": event["format"],
            "badge": event["badge"],
            "theme": event["theme"],
            "shows": shows,
        }

    def _build_show_chip(self, show: ShowState, selected_show_id: str) -> dict[str, Any]:
        available = self._show_available_count(show)
        sold_out = available == 0
        return {
            "show_id": show.show_id,
            "label": show.label,
            "date_label": show.date_label,
            "auditorium": show.auditorium,
            "available_label": "Sold out" if sold_out else f"{available} seats left",
            "selected": show.show_id == selected_show_id,
            "sold_out": sold_out,
        }

    def _build_show_view(self, show: ShowState) -> dict[str, Any]:
        with show.lock:
            rows: list[dict[str, Any]] = []
            seat_counts = Counter()
            for row_def in show.row_layout:
                row_seats: list[dict[str, Any]] = []
                for number in range(1, row_def["count"] + 1):
                    seat = show.seats[f"{row_def['row']}{number}"]
                    row_seats.append(
                        {
                            "seat_id": seat.seat_id,
                            "label": str(number),
                            "status": seat.status,
                            "zone": seat.zone,
                            "price": seat.price,
                            "gap_after": number in row_def["aisles"],
                        }
                    )
                    seat_counts[seat.status] += 1
                rows.append(
                    {
                        "row_label": row_def["row"],
                        "zone": row_def["zone"],
                        "seats": row_seats,
                    }
                )

        return {
            "show_id": show.show_id,
            "label": show.label,
            "date_label": show.date_label,
            "auditorium": show.auditorium,
            "experience": show.experience,
            "screen_label": "All eyes this way please",
            "rows": rows,
            "legend": [
                {"status": "available", "label": "Available"},
                {"status": "processing", "label": "Being booked"},
                {"status": "sold", "label": "Sold"},
            ],
            "price_bands": [
                {
                    "zone": zone,
                    "price_label": f"Rs. {price:,}",
                    "available_label": f"{self._zone_available_count(show, zone)} seats",
                }
                for zone, price in ZONE_PRICING.items()
            ],
            "stats": {
                "available": seat_counts["available"],
                "processing": seat_counts["processing"],
                "sold": seat_counts["sold"],
            },
        }

    def _build_recent_bookings(self) -> list[dict[str, Any]]:
        bookings = [
            booking
            for booking in (self._build_order_view(order) for order in self._orders.values())
            if booking["confirmed_seats"]
        ]
        bookings.sort(key=lambda item: item["created_at_value"], reverse=True)
        return bookings[:6]

    def _build_order_view(self, order: BookingOrder) -> dict[str, Any]:
        event = self._events[order.event_id]
        show = self._shows[order.show_id]
        confirmed: list[str] = []
        unavailable: list[str] = []
        processing: list[str] = []
        total = 0

        with show.lock:
            for seat_id in order.requested_seats:
                seat = show.seats.get(seat_id)
                if seat is None:
                    unavailable.append(seat_id)
                    continue
                if seat.status == "sold" and seat.order_id == order.order_id:
                    confirmed.append(seat_id)
                    total += seat.price
                elif seat.status == "processing" and seat.order_id == order.order_id:
                    processing.append(seat_id)
                else:
                    unavailable.append(seat_id)

        if len(confirmed) == len(order.requested_seats) and confirmed:
            status = "Confirmed"
            status_tone = "success"
        elif confirmed and unavailable:
            status = "Partially confirmed"
            status_tone = "warning"
        elif processing:
            status = "Processing"
            status_tone = "info"
        else:
            status = "Unavailable"
            status_tone = "danger"

        return {
            "order_id": order.order_id,
            "customer_name": order.customer_name,
            "email": order.email,
            "event_title": event["title"],
            "event_subtitle": event["subtitle"],
            "show_label": show.label,
            "date_label": show.date_label,
            "auditorium": show.auditorium,
            "requested_seats": order.requested_seats,
            "confirmed_seats": confirmed,
            "unavailable_seats": unavailable,
            "processing_seats": processing,
            "seat_summary": ", ".join(confirmed or order.requested_seats),
            "amount_label": f"Rs. {total:,}",
            "status": status,
            "status_tone": status_tone,
            "created_label": self._relative_time(order.created_at),
            "created_at_value": order.created_at,
        }

    def _resolve_event(self, event_id: str | None) -> dict[str, Any]:
        if event_id and event_id in self._events:
            return self._events[event_id]
        return next(iter(self._events.values()))

    def _resolve_show(self, event_id: str, show_id: str | None) -> ShowState:
        event = self._events[event_id]
        if show_id and show_id in self._shows and self._shows[show_id].event_id == event_id:
            return self._shows[show_id]
        return self._shows[event["show_ids"][0]]

    def _show_available_count(self, show: ShowState) -> int:
        with show.lock:
            return sum(1 for seat in show.seats.values() if seat.status == "available")

    def _zone_available_count(self, show: ShowState, zone: str) -> int:
        with show.lock:
            return sum(1 for seat in show.seats.values() if seat.zone == zone and seat.status == "available")

    def _sort_seat_ids(self, seat_ids: list[str]) -> list[str]:
        cleaned = sorted({seat_id.strip().upper() for seat_id in seat_ids if seat_id.strip()})
        return sorted(cleaned, key=lambda value: (value[0], int(value[1:])))

    def _derive_priority(self, zone: str) -> int:
        return {"Platinum": 9, "Gold": 7, "Silver": 5}[zone]

    def _derive_burst_time(self, zone: str) -> float:
        return {"Platinum": 0.01, "Gold": 0.013, "Silver": 0.016}[zone]

    def _derive_pages(self, zone: str) -> int:
        return {"Platinum": 5, "Gold": 4, "Silver": 3}[zone]

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            pid = self.kernel.run_scheduler_step()
            if pid is None:
                self._stop_event.wait(0.05)
            else:
                self._stop_event.wait(0.01)

    def _pulse_loop(self) -> None:
        while not self._stop_event.wait(2.5):
            self._sync_runtime_state()
            process_snapshot = self.kernel.process_manager.snapshot()
            active_pids = [
                int(proc["pid"])
                for proc in process_snapshot["processes"]
                if proc["state"] != ProcessState.TERMINATED.value
            ]
            if active_pids:
                self.kernel.memory_manager.simulate_thrashing(active_pids[: min(24, len(active_pids))], rounds=40)
            requests = [(int(pid) * 11) % 200 for pid in process_snapshot["ready_queue"][:10]] or [17, 31, 74, 106]
            self.kernel.file_manager.schedule_requests(requests, algorithm="SCAN")

    def _relative_time(self, timestamp: float) -> str:
        delta = max(int(time.time() - timestamp), 0)
        if delta < 5:
            return "just now"
        if delta < 60:
            return f"{delta}s ago"
        minutes = delta // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"

    def _drain_events(self) -> None:
        self.kernel.sys_event_queue.join()
