/* ============================================================
   ShowGrid — Ticketing Platform Frontend
   OS Concepts: FCFS scheduling, mutex seat locking, semaphores
   ============================================================ */

const state = {
  dashboard: null,
  eventId: null,
  showId: null,
  selectedSeats: [],
  searchTerm: "",
  myBookings: [],
  osOpen: false,
};

const refs = {
  eventSearch:      document.querySelector("#event-search"),
  bannerCard:       document.querySelector("#banner-card"),
  eventBadge:       document.querySelector("#event-badge"),
  eventTitle:       document.querySelector("#event-title"),
  eventSubtitle:    document.querySelector("#event-subtitle"),
  eventAbout:       document.querySelector("#event-about"),
  eventFormat:      document.querySelector("#event-format"),
  eventLanguage:    document.querySelector("#event-language"),
  eventDuration:    document.querySelector("#event-duration"),
  eventVenue:       document.querySelector("#event-venue"),
  eventPoster:      document.querySelector("#event-poster"),
  posterTitle:      document.querySelector("#poster-title"),
  eventsGrid:       document.querySelector("#events-grid"),
  showtimeList:     document.querySelector("#showtime-list"),
  selectedShowTitle:document.querySelector("#selected-show-title"),
  selectedShowCopy: document.querySelector("#selected-show-copy"),
  seatStats:        document.querySelector("#seat-stats"),
  priceBands:       document.querySelector("#price-bands"),
  legend:           document.querySelector("#legend"),
  seatMap:          document.querySelector("#seat-map"),
  summaryEvent:     document.querySelector("#summary-event"),
  summaryShow:      document.querySelector("#summary-show"),
  summaryPosterMini:document.querySelector("#summary-poster-mini"),
  selectedSeats:    document.querySelector("#selected-seats"),
  seatCountBadge:   document.querySelector("#seat-count-badge"),
  summaryTotal:     document.querySelector("#summary-total"),
  bookingForm:      document.querySelector("#booking-form"),
  bookButton:       document.querySelector("#book-button"),
  formFeedback:     document.querySelector("#form-feedback"),
  recentBookings:   document.querySelector("#recent-bookings"),
  // OS panel
  osPanelToggle:    document.querySelector("#os-panel-toggle"),
  osPanelSection:   document.querySelector(".os-panel-section"),
  osScheduler:      document.querySelector("#os-scheduler"),
  osWorkers:        document.querySelector("#os-workers"),
  osLoad:           document.querySelector("#os-load"),
  // Modal
  myBookingsBtn:    document.querySelector("#my-bookings-btn"),
  bookingsModal:    document.querySelector("#bookings-modal"),
  modalCloseBtn:    document.querySelector("#modal-close-btn"),
  modalBookingsList:document.querySelector("#modal-bookings-list"),
  // Toast
  successToast:     document.querySelector("#success-toast"),
  toastMessage:     document.querySelector("#toast-message"),
};

/* ============================================================
   UTILITIES
   ============================================================ */
const esc = (v) =>
  String(v).replaceAll("&","&amp;").replaceAll("<","&lt;")
           .replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");

function sortSeatIds(ids) {
  return [...ids].sort((a, b) => {
    const ra = a[0], rb = b[0];
    if (ra !== rb) return ra.localeCompare(rb);
    return Number(a.slice(1)) - Number(b.slice(1));
  });
}

function getSeatLookup() {
  const show = state.dashboard?.selected_show;
  const map = new Map();
  for (const row of (show?.rows || [])) {
    for (const seat of (row.seats || [])) map.set(seat.seat_id, seat);
  }
  return map;
}

function reconcileSelectedSeats() {
  const lookup = getSeatLookup();
  state.selectedSeats = state.selectedSeats.filter(id => lookup.get(id)?.status === "available");
}

function setFeedback(msg, tone = "") {
  refs.formFeedback.textContent = msg;
  refs.formFeedback.className = "form-feedback" + (tone ? ` is-${tone}` : "");
}

function showToast(msg) {
  refs.toastMessage.textContent = msg;
  refs.successToast.classList.remove("hidden");
  setTimeout(() => refs.successToast.classList.add("hidden"), 5000);
}

/* ============================================================
   RENDER: BANNER
   ============================================================ */
function renderBanner() {
  const ev = state.dashboard.selected_event;
  refs.bannerCard.className  = `banner-card ${esc(ev.theme)}`;
  refs.eventPoster.className = `poster-card ${esc(ev.theme)}`;
  refs.eventBadge.textContent    = ev.badge;
  refs.eventTitle.textContent    = ev.title;
  refs.eventSubtitle.textContent = ev.subtitle;
  refs.eventAbout.textContent    = ev.about;
  refs.eventFormat.textContent   = ev.format;
  refs.eventLanguage.textContent = ev.language;
  refs.eventDuration.textContent = ev.duration;
  refs.eventVenue.textContent    = ev.venue;
  refs.posterTitle.textContent   = ev.title;
}

/* ============================================================
   RENDER: EVENTS GRID
   ============================================================ */
function renderEvents() {
  const term = state.searchTerm.trim().toLowerCase();
  const events = (state.dashboard.events || []).filter(ev => {
    if (!term) return true;
    return [ev.title, ev.subtitle, ev.venue, ev.format, ev.language]
      .join(" ").toLowerCase().includes(term);
  });

  if (!events.length) {
    refs.eventsGrid.innerHTML = `<div class="empty-state">No events matched that search. Try another title, venue, or genre.</div>`;
    return;
  }

  refs.eventsGrid.innerHTML = events.map(ev => `
    <article class="event-card ${esc(ev.theme)} ${ev.selected ? "is-selected" : ""}" data-event-id="${esc(ev.event_id)}" role="button" tabindex="0" aria-label="Select ${esc(ev.title)}">
      <div class="poster-thumb">
        <span class="poster-thumb-badge">${esc(ev.badge)}</span>
        <strong class="poster-thumb-title">${esc(ev.title)}</strong>
      </div>
      <div class="event-body">
        <div>
          <h3 class="event-card-title">${esc(ev.title)}</h3>
          <p class="event-card-sub">${esc(ev.subtitle)}</p>
        </div>
        <div class="event-card-meta">
          <span class="event-card-chip">${esc(ev.format)}</span>
          <span class="event-card-chip">${esc(ev.language)}</span>
          <span class="event-card-chip">${esc(ev.venue)}</span>
        </div>
        <p class="event-card-price">${esc(ev.starting_price_label)}</p>
        <p class="event-card-sub">${esc(ev.available_label)}</p>
      </div>
    </article>
  `).join("");
}

/* ============================================================
   RENDER: SHOWTIMES
   ============================================================ */
function renderShowtimes() {
  const shows = state.dashboard.selected_event.shows || [];
  refs.showtimeList.innerHTML = shows.map(show => `
    <button type="button"
      class="show-chip ${show.selected ? "is-selected" : ""} ${show.sold_out ? "is-sold-out" : ""}"
      data-show-id="${esc(show.show_id)}"
      ${show.sold_out ? "disabled" : ""}
      aria-pressed="${show.selected}"
    >
      <div class="show-chip-time">${esc(show.label)}</div>
      <div class="show-chip-date">${esc(show.date_label)}</div>
      <div class="show-chip-venue">${esc(show.auditorium)}</div>
      <div class="show-chip-avail">${esc(show.available_label)}</div>
    </button>
  `).join("");
}

/* ============================================================
   RENDER: PRICE BANDS
   ============================================================ */
function renderPriceBands(show) {
  refs.priceBands.innerHTML = (show.price_bands || []).map(band => `
    <div class="price-band">
      <span class="price-band-zone">${esc(band.zone)}</span>
      <span class="price-band-price">${esc(band.price_label)}</span>
      <span class="price-band-avail">${esc(band.available_label)}</span>
    </div>
  `).join("");
}

/* ============================================================
   RENDER: LEGEND
   ============================================================ */
function renderLegend(show) {
  const items = [
    ...(show.legend || []),
    { status: "selected", label: "Your selection" },
  ];
  refs.legend.innerHTML = items.map(item => `
    <div class="legend-item">
      <span class="legend-swatch ${esc(item.status)}"></span>
      <span>${esc(item.label)}</span>
    </div>
  `).join("");
}

/* ============================================================
   RENDER: SEAT MAP
   ============================================================ */
function renderSeatMap(show) {
  refs.selectedShowTitle.textContent = `${show.label} — ${show.auditorium}`;
  refs.selectedShowCopy.textContent  = `${show.date_label} · ${show.experience}`;

  const { available, sold, processing } = show.stats;
  refs.seatStats.innerHTML = `
    <div class="seat-stats-main">${esc(String(available))} available</div>
    <div class="seat-stats-sub">${esc(String(sold))} sold · ${esc(String(processing))} being booked</div>
  `;

  refs.seatMap.innerHTML = (show.rows || []).map(row => `
    <div class="seat-row">
      <div class="row-label">${esc(row.row_label)}</div>
      <div class="row-seats">
        ${row.seats.map(seat => {
          const isSel = state.selectedSeats.includes(seat.seat_id);
          const disabled = seat.status !== "available";
          return `<button
            type="button"
            class="seat-button ${esc(seat.status)} ${isSel ? "is-selected" : ""} ${seat.gap_after ? "gap-after" : ""}"
            data-seat-id="${esc(seat.seat_id)}"
            ${disabled ? "disabled" : ""}
            title="${esc(seat.seat_id)} · ${esc(seat.zone)} · ₹${esc(seat.price)}"
            aria-label="Seat ${esc(seat.seat_id)}, ${esc(seat.zone)}, ₹${esc(seat.price)}, ${esc(seat.status)}"
            aria-pressed="${isSel}"
          >${esc(seat.label)}</button>`;
        }).join("")}
      </div>
    </div>
  `).join("");
}

/* ============================================================
   RENDER: SUMMARY
   ============================================================ */
function renderSummary() {
  const ev   = state.dashboard.selected_event;
  const show = state.dashboard.selected_show;
  const lookup = getSeatLookup();

  const details = state.selectedSeats
    .map(id => lookup.get(id)).filter(Boolean)
    .sort((a, b) => a.seat_id.localeCompare(b.seat_id));

  const total = details.reduce((s, seat) => s + seat.price, 0);

  refs.summaryEvent.textContent = ev.title;
  refs.summaryShow.textContent  = `${show.date_label} · ${show.label}`;
  refs.summaryTotal.textContent = `₹${total.toLocaleString("en-IN")}`;
  refs.seatCountBadge.textContent = `${details.length} seat${details.length !== 1 ? "s" : ""}`;

  // Mini poster
  refs.summaryPosterMini.className = `summary-event-poster ${esc(ev.theme)}`;

  if (!details.length) {
    refs.selectedSeats.innerHTML = `
      <div class="empty-seat-prompt">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 9V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v2"/><path d="M2 11v5a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v1H6v-1a2 2 0 0 0-4 0z"/></svg>
        No seats selected yet
      </div>`;
    return;
  }

  refs.selectedSeats.innerHTML = details.map(seat => `
    <span class="selected-seat-pill">
      <strong>${esc(seat.seat_id)}</strong>
      <span>${esc(seat.zone)} · ₹${esc(seat.price)}</span>
      <button class="seat-pill-remove" data-remove-seat="${esc(seat.seat_id)}" title="Remove seat ${esc(seat.seat_id)}" aria-label="Remove seat ${esc(seat.seat_id)}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6 6 18M6 6l12 12"/></svg>
      </button>
    </span>
  `).join("");
}

/* ============================================================
   RENDER: RECENT BOOKINGS
   ============================================================ */
function renderRecentBookings() {
  const bookings = state.dashboard.recent_bookings || [];
  if (!bookings.length) {
    refs.recentBookings.innerHTML = `<div class="empty-state">New confirmations will appear here after the first booking.</div>`;
    return;
  }

  refs.recentBookings.innerHTML = bookings.map(b => `
    <article class="recent-card">
      <div class="recent-head">
        <div>
          <p class="recent-order-id">${esc(b.order_id)}</p>
          <h3 class="recent-event-title">${esc(b.event_title)}</h3>
        </div>
        <span class="status-pill ${esc(b.status_tone)}">${esc(b.status)}</span>
      </div>
      <p class="recent-meta">${esc(b.show_label)} · ${esc(b.date_label)}</p>
      <p class="recent-meta">${esc(b.auditorium)}</p>
      <p class="recent-body"><strong>Seats:</strong> ${esc(b.seat_summary)}</p>
      <p class="recent-body"><strong>Total:</strong> ${esc(b.amount_label)}</p>
      <p class="recent-meta">${esc(b.customer_name)} · ${esc(b.created_label)}</p>
    </article>
  `).join("");
}

/* ============================================================
   RENDER: OS METRICS
   ============================================================ */
function renderOSMetrics() {
  const meta = state.dashboard?.meta;
  if (!meta) return;
  if (refs.osWorkers) refs.osWorkers.textContent = meta.workers > 0 ? String(meta.workers) : "—";
  if (refs.osLoad)    refs.osLoad.textContent    = meta.load_sample > 0 ? `${meta.load_sample}ms` : "—";
}

/* ============================================================
   RENDER: MY BOOKINGS MODAL
   ============================================================ */
function renderModalBookings() {
  const bookings = state.dashboard?.recent_bookings || [];
  if (!bookings.length) {
    refs.modalBookingsList.innerHTML = `<p class="modal-empty">No bookings yet. Book some seats to see them here!</p>`;
    return;
  }
  refs.modalBookingsList.innerHTML = bookings.map(b => `
    <div class="modal-booking-row">
      <div class="recent-head">
        <div>
          <p class="recent-order-id">${esc(b.order_id)}</p>
          <h3 class="recent-event-title">${esc(b.event_title)}</h3>
        </div>
        <span class="status-pill ${esc(b.status_tone)}">${esc(b.status)}</span>
      </div>
      <p class="recent-meta">${esc(b.show_label)} · ${esc(b.date_label)} · ${esc(b.auditorium)}</p>
      <p class="recent-body"><strong>Seats:</strong> ${esc(b.seat_summary)} &nbsp;|&nbsp; <strong>Total:</strong> ${esc(b.amount_label)}</p>
      <p class="recent-meta">Booked by ${esc(b.customer_name)} · ${esc(b.created_label)}</p>
    </div>
  `).join("");
}

/* ============================================================
   MASTER RENDER
   ============================================================ */
function render() {
  if (!state.dashboard) return;
  renderBanner();
  renderEvents();
  renderShowtimes();
  renderPriceBands(state.dashboard.selected_show);
  renderLegend(state.dashboard.selected_show);
  renderSeatMap(state.dashboard.selected_show);
  renderSummary();
  renderRecentBookings();
  renderOSMetrics();
}

/* ============================================================
   DATA LOADING
   ============================================================ */
async function loadDashboard(silent = false) {
  const params = new URLSearchParams();
  if (state.eventId) params.set("event", state.eventId);
  if (state.showId)  params.set("show", state.showId);

  try {
    const res = await fetch(`/api/dashboard${params.toString() ? `?${params}` : ""}`, {
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error("Unable to load ticketing data right now.");

    state.dashboard = await res.json();
    state.eventId   = state.dashboard.selected_event.event_id;
    state.showId    = state.dashboard.selected_show.show_id;
    reconcileSelectedSeats();
    render();
  } catch (err) {
    if (!silent) setFeedback(err.message || "Unable to load the booking page.", "error");
  }
}

/* ============================================================
   SEAT TOGGLE
   ============================================================ */
function toggleSeat(seatId) {
  if (state.selectedSeats.includes(seatId)) {
    state.selectedSeats = state.selectedSeats.filter(id => id !== seatId);
  } else {
    if (state.selectedSeats.length >= 8) {
      setFeedback("You can select up to 8 seats per booking.", "error");
      setTimeout(() => setFeedback(""), 3000);
      return;
    }
    state.selectedSeats = sortSeatIds([...state.selectedSeats, seatId]);
  }
  renderSummary();
  renderSeatMap(state.dashboard.selected_show);
}

/* ============================================================
   BOOKING SUBMISSION
   ============================================================ */
async function submitBooking(event) {
  event.preventDefault();
  if (!state.selectedSeats.length) {
    setFeedback("Select one or more seats before continuing.", "error");
    return;
  }

  refs.bookButton.disabled = true;
  refs.bookButton.querySelector(".btn-text").textContent = "Processing…";
  setFeedback("Acquiring seat locks via kernel mutex…");

  const fd = new FormData(refs.bookingForm);
  const payload = {
    customer_name: fd.get("customer_name"),
    email:         fd.get("email"),
    event_id:      state.eventId,
    show_id:       state.showId,
    seat_ids:      state.selectedSeats,
  };

  try {
    const res = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Booking could not be completed.");

    // Success
    setFeedback(data.message, "success");
    showToast(data.message);
    state.selectedSeats = [];
    refs.bookingForm.reset();
    await loadDashboard();
  } catch (err) {
    setFeedback(err.message || "Booking could not be completed.", "error");
  } finally {
    refs.bookButton.disabled = false;
    refs.bookButton.querySelector(".btn-text").textContent = "Confirm Booking";
  }
}

/* ============================================================
   EVENT LISTENERS
   ============================================================ */

// Event card click + keyboard
refs.eventsGrid.addEventListener("click", async (e) => {
  const card = e.target.closest("[data-event-id]");
  if (!card) return;
  state.eventId = card.dataset.eventId;
  state.showId  = null;
  state.selectedSeats = [];
  await loadDashboard();
  document.querySelector(".booking-shell").scrollIntoView({ behavior: "smooth" });
});

refs.eventsGrid.addEventListener("keydown", async (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = e.target.closest("[data-event-id]");
  if (!card) return;
  e.preventDefault();
  state.eventId = card.dataset.eventId;
  state.showId  = null;
  state.selectedSeats = [];
  await loadDashboard();
});

// Showtime click
refs.showtimeList.addEventListener("click", async (e) => {
  const chip = e.target.closest("[data-show-id]");
  if (!chip) return;
  state.showId = chip.dataset.showId;
  state.selectedSeats = [];
  await loadDashboard();
});

// Seat click
refs.seatMap.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-seat-id]");
  if (!btn) return;
  toggleSeat(btn.dataset.seatId);
});

// Remove seat pill
refs.selectedSeats.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-remove-seat]");
  if (!btn) return;
  toggleSeat(btn.dataset.removeSeat);
});

// Search
refs.eventSearch.addEventListener("input", (e) => {
  state.searchTerm = e.target.value || "";
  renderEvents();
});

// Form submit
refs.bookingForm.addEventListener("submit", submitBooking);

// OS panel toggle
refs.osPanelToggle.addEventListener("click", () => {
  state.osOpen = !state.osOpen;
  refs.osPanelSection.classList.toggle("is-open", state.osOpen);
});

// My Bookings modal
refs.myBookingsBtn.addEventListener("click", () => {
  renderModalBookings();
  refs.bookingsModal.classList.remove("hidden");
});

refs.modalCloseBtn.addEventListener("click", () => {
  refs.bookingsModal.classList.add("hidden");
});

refs.bookingsModal.addEventListener("click", (e) => {
  if (e.target === refs.bookingsModal) refs.bookingsModal.classList.add("hidden");
});

// Filter chips (client-side only — filters by text match)
document.querySelector(".filter-row")?.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-filter]");
  if (!chip) return;

  document.querySelectorAll(".filter-chip").forEach(c => c.classList.remove("active"));
  chip.classList.add("active");

  const filter = chip.dataset.filter;
  const filterMap = { concert: "concert", comedy: "comedy", theatre: "theatre" };
  if (filter === "all") {
    state.searchTerm = "";
  } else {
    state.searchTerm = filterMap[filter] || "";
  }
  refs.eventSearch.value = state.searchTerm;
  renderEvents();
});

/* ============================================================
   INIT
   ============================================================ */
loadDashboard().catch(err => {
  setFeedback(err.message || "Unable to load the booking page.", "error");
});

// Live polling every 5 seconds (simulates real-time seat sync via kernel pulse loop)
setInterval(() => {
  loadDashboard(true).catch(() => {});
}, 5000);
