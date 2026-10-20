"use strict";
const $ = (selector) => document.querySelector(selector);
const state = {
  session: null,
  data: null,
  page: "overview",
  selected: null,
  hours: 24,
  search: "",
  filter: "",
  incidentFilter: "",
  offset: 0,
  detailOffset: 0,
  renderId: 0,
  refreshing: false,
  editing: null,
};
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
const icon = (name) =>
  `<svg class="ui-icon" aria-hidden="true"><use href="/assets/icons.svg#${name}"></use></svg>`;
const badge = (status) =>
  `<span class="badge ${escape(status)}">${escape(status.replaceAll("_", " "))}</span>`;
const date = (value) =>
  value
    ? new Date(value).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Not observed";
const age = (value) => {
  if (!value) return "Awaiting first check";
  const seconds = Math.max(
    0,
    Math.round((Date.now() - Date.parse(value)) / 1000),
  );
  return seconds < 60
    ? `${seconds}s ago`
    : seconds < 3600
      ? `${Math.floor(seconds / 60)}m ago`
      : `${Math.floor(seconds / 3600)}h ago`;
};
const percentage = (value) =>
  value === null || value === undefined ? "—" : `${Number(value).toFixed(1)}%`;
const duration = (value) =>
  value === null || value === undefined
    ? "—"
    : `${Math.round(value * 1000)} ms`;
const serviceName = (id) =>
  state.data?.services.find((service) => service.id === id)?.name ||
  "Removed service";
const empty = (title, description, action = "", compact = false) =>
  `<div class="empty ${compact ? "compact" : ""}"><span class="empty-symbol" aria-hidden="true">${icon("overview")}</span><h3>${escape(title)}</h3><p>${escape(description)}</p>${action}</div>`;
const config = (service) =>
  Object.fromEntries(
    [
      "name",
      "url",
      "enabled",
      "check_interval_seconds",
      "timeout_seconds",
      "failure_threshold",
      "expected_status",
    ].map((key) => [key, service[key]]),
  );

function showLogin(message = "") {
  if ($("#service-dialog").open) $("#service-dialog").close();
  $("#toast").hidden = true;
  $("#view").replaceChildren();
  state.session = null;
  state.data = null;
  state.renderId++;
  $("#workspace").hidden = true;
  $("#login-screen").hidden = false;
  $("#login-error").textContent = message;
  $("#login-error").hidden = !message;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 4500);
}
function banner(message) {
  $("#workspace-error").textContent = message;
  $("#workspace-error").hidden = !message;
}
async function api(path, options = {}) {
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(state.session ? { "X-CSRF-Token": state.session.csrf_token } : {}),
    ...options.headers,
  };
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
    headers,
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    const message =
      data?.error?.message || "The request could not be completed.";
    if (response.status === 401 && !path.endsWith("/login"))
      showLogin("Your session has expired. Sign in to continue.");
    let detail = data?.error?.details?.[0]?.message;
    throw new Error(detail ? `${message}: ${detail}` : message);
  }
  return data;
}
async function refresh() {
  if (!state.session || state.refreshing) return;
  state.refreshing = true;
  $("#refresh").disabled = true;
  try {
    const data = await api(`/api/v1/dashboard?window_hours=${state.hours}`);
    if (!state.session) return;
    state.data = data;
    banner("");
    $("#environment").textContent = data.environment;
    $("#sync-status").textContent =
      `Last refreshed ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
    $("#collector-label").textContent = data.scheduler_enabled
      ? "Monitoring active"
      : "Scheduled checks paused";
    $("#collector-dot").className =
      `dot ${data.scheduler_enabled ? "green" : "gray"}`;
    $("#incident-badge").hidden = !data.open_incidents;
    $("#incident-badge").textContent = data.open_incidents;
    await render();
  } catch (error) {
    if (state.session) {
      banner(`${error.message} Displayed observations may be out of date.`);
      $("#sync-status").textContent = "Unable to refresh";
    }
  } finally {
    state.refreshing = false;
    $("#refresh").disabled = false;
  }
}
function navigate(page, id = null) {
  state.page = page;
  state.selected = id;
  state.offset = 0;
  state.detailOffset = 0;
  render();
}
function stat(label, value, detail, symbol, theme = "") {
  return `<article class="stat ${theme}"><span class="stat-label">${label}</span><span class="stat-symbol" aria-hidden="true">${icon(symbol)}</span><div class="stat-number">${value}</div><span class="stat-detail">${detail}</span></article>`;
}
function overviewStats() {
  const data = state.data,
    summaries = data.availability;
  const successes = summaries.reduce((sum, row) => sum + row.successes, 0),
    failures = summaries.reduce((sum, row) => sum + row.failures, 0);
  const truncated = summaries.some((row) => row.history_may_be_truncated);
  return `<section class="stats" aria-label="Workspace summary">${stat("Registered services", data.total, `${data.counts.paused} paused · ${data.counts.unknown} awaiting checks`, "services")}${stat("Last check healthy", data.counts.healthy, "Latest known service observations", "arrow", "good")}${stat("Open incidents", data.open_incidents, data.open_incidents ? "Services needing your attention" : "No unresolved incidents", "flag", data.open_incidents ? "attention" : "")}${stat("Observed success", percentage(successes + failures ? (100 * successes) / (successes + failures) : null), `${successes + failures} valid checks${truncated ? " · limited history" : ""}`, "clock")}</section>`;
}
function serviceRows(services) {
  return services
    .map((service) => {
      const summary = state.data.availability.find(
        (item) => item.service_id === service.id,
      );
      const overdue =
        service.enabled &&
        service.last_checked_at &&
        (Date.now() - Date.parse(service.last_checked_at)) / 1000 >
          service.check_interval_seconds * 2 + service.timeout_seconds;
      return `<tr><td><div class="service-cell"><span class="service-icon" aria-hidden="true">${icon("pulse")}</span><div><button class="service-link" data-service="${escape(service.id)}">${escape(service.name)}</button><span class="url-label" title="${escape(service.url)}">${escape(service.url)}</span></div></div></td><td>${badge(service.status)}${overdue ? '<span class="notification-error">Observation overdue</span>' : ""}</td><td class="mono">${service.last_status_code === null ? "—" : duration(service.last_duration_seconds)}</td><td class="mono">${percentage(summary?.success_percentage)}</td><td>${escape(age(service.last_checked_at))}</td><td><button class="row-action" data-service="${escape(service.id)}" aria-label="View ${escape(service.name)}">${icon("arrow")}</button></td></tr>`;
    })
    .join("");
}
function inventory(full = false) {
  const services = state.data.services.filter(
    (service) =>
      (!state.filter || service.status === state.filter) &&
      `${service.name} ${service.url}`
        .toLowerCase()
        .includes(state.search.toLowerCase()),
  );
  return `<section class="panel"><div class="panel-header"><div><h2>${full ? "Your services" : "Service health"}<span class="count-label">${services.length} services</span></h2><p>Latest results from your registered health checks.</p></div><div class="filters"><label class="sr-only" for="search">Search services</label><input class="search" id="search" type="search" placeholder="Search services…" value="${escape(state.search)}"><label class="sr-only" for="status-filter">Filter service status</label><select id="status-filter"><option value="">All statuses</option>${["healthy", "failing", "down", "blocked", "paused", "unknown"].map((status) => `<option value="${status}" ${state.filter === status ? "selected" : ""}>${status[0].toUpperCase() + status.slice(1)}</option>`).join("")}</select></div></div>${services.length ? `<div class="table-scroll"><table><thead><tr><th>Service</th><th>Last result</th><th>Response time</th><th>Observed success</th><th>Last checked</th><th><span class="sr-only">Details</span></th></tr></thead><tbody>${serviceRows(services)}</tbody></table></div>` : empty(state.data.total ? "No services match" : "Your first service starts here", state.data.total ? "Try a different search or status filter." : "Add an approved health endpoint to start collecting real observations.", state.data.total ? "" : '<button class="button primary" data-add>+ Add a service</button>')}<div class="panel-footer"><span>Check success is based on retained observations.</span><span>Window: ${state.hours === 168 ? "7 days" : state.hours + "h"}</span></div></section>`;
}
function recentIncidents() {
  const incidents = state.data.incidents.slice(0, 4);
  return `<section class="panel"><div class="panel-header"><div><h2>Incidents needing attention</h2><p>Unresolved issues across your services.</p></div><button class="text-button" data-nav="incidents">View all →</button></div>${incidents.length ? incidents.map((item) => `<div class="incident-item"><span class="incident-mark" aria-hidden="true">!</span><div><h3>${escape(serviceName(item.service_id))}</h3><p>${escape(item.reason)} · ${escape(age(item.opened_at))}</p></div>${badge("open")}</div>`).join("") : empty("All clear for now", "No open incidents. New services still need their first observation.", "", true)}</section>`;
}
function guidance() {
  const data = state.data;
  return `<section class="panel"><div class="panel-header"><h2>Monitoring at a glance</h2></div><div class="panel-body"><div class="key-value"><span>Automatic checks</span><strong>${data.scheduler_enabled ? "Enabled" : "Paused"}</strong></div><div class="key-value"><span>Alert destination</span><strong>${data.webhook_configured ? "Webhook connected" : "Not connected"}</strong></div><div class="key-value"><span>Observation window</span><strong>${state.hours === 168 ? "Last 7 days" : state.hours === 1 ? "Last hour" : "Last 24 hours"}</strong></div><div class="explanation"><h3>Observations, without assumptions.</h3><p>Missing or blocked checks never count as successful. Paused services keep their history, and incidents stay open until a recovery is observed.</p></div></div></section>`;
}
function paging(count, detail = false) {
  const offset = detail ? state.detailOffset : state.offset;
  return `<div class="pagination"><button data-page="prev" ${detail ? "data-detail" : ""} ${offset === 0 ? "disabled" : ""}>Previous</button><span>${offset + 1}${count ? "–" + (offset + count) : ""}</span><button data-page="next" ${detail ? "data-detail" : ""} ${count < 50 ? "disabled" : ""}>Next</button></div>`;
}
function chart(checks, service) {
  if (!checks.length)
    return empty(
      "Waiting for observations",
      "Response times appear after the first completed check.",
      "",
      true,
    );
  const samples = [...checks].reverse(),
    known = samples.filter((check) => check.outcome !== "blocked");
  const maximum = Math.max(
    0.01,
    ...known.map((check) => check.duration_seconds),
  );
  const start = Date.parse(samples[0].checked_at),
    end = Math.max(start + 1, Date.parse(samples.at(-1).checked_at));
  const x = (check) =>
    55 + ((Date.parse(check.checked_at) - start) / (end - start)) * 715;
  const y = (check) => 165 - (check.duration_seconds / maximum) * 135;
  let path = "",
    previous = null;
  const points = samples
    .map((check) => {
      if (check.outcome === "blocked") {
        previous = null;
        return "";
      }
      const connected =
        previous &&
        Date.parse(check.checked_at) - Date.parse(previous.checked_at) <
          service.check_interval_seconds * 1500;
      path += `${connected ? "L" : "M"}${x(check).toFixed(1)} ${y(check).toFixed(1)} `;
      previous = check;
      return `<circle cx="${x(check).toFixed(1)}" cy="${y(check).toFixed(1)}" r="4" fill="${check.outcome === "success" ? "#629b78" : "#c47762"}" stroke="white" stroke-width="2"><title>${escape(date(check.checked_at))}: ${escape(check.outcome)} · ${duration(check.duration_seconds)}</title></circle>`;
    })
    .join("");
  return `<svg class="chart" viewBox="0 0 800 215" role="img" aria-label="Response duration for the latest observations"><title>Latest response durations</title><desc>Measured probe durations. Gaps do not imply continuous availability.</desc>${[0, 0.5, 1].map((factor) => `<path class="grid" d="M55 ${165 - factor * 135}H775"/><text x="5" y="${169 - factor * 135}">${Math.round(maximum * factor * 1000)}ms</text>`).join("")}<path class="line" d="${path}"/>${points}<text x="55" y="199">${escape(date(samples[0].checked_at))}</text><text x="770" y="199" text-anchor="end">${escape(date(samples.at(-1).checked_at))}</text></svg><div class="chart-legend"><span><span class="dot green"></span>Successful check</span><span><span class="dot red"></span>Failed check</span></div><p class="chart-caption">Latest ${checks.length} retained observations. Blocked checks and long gaps are not connected.</p>`;
}
async function detailView(id) {
  const service = state.data.services.find(
    (service) => service.id === state.selected,
  );
  if (!service) {
    state.page = "services";
    state.selected = null;
    return render();
  }
  const [checks, summary] = await Promise.all([
    api(
      `/api/v1/services/${encodeURIComponent(service.id)}/checks?limit=50&offset=${state.detailOffset}`,
    ),
    api(
      `/api/v1/services/${encodeURIComponent(service.id)}/availability?window_hours=${state.hours}`,
    ),
  ]);
  if (id !== state.renderId) return;
  const warning = summary.history_may_be_truncated
    ? '<p class="warning-note">Older observations have been removed by retention. This window may be incomplete.</p>'
    : "";
  $("#view").innerHTML =
    `<div class="detail-toolbar"><button class="text-button" data-nav="services">← All services</button><button class="button secondary" data-check="${escape(service.id)}" ${service.enabled ? "" : "disabled"}>Check now</button><button class="button secondary" data-pause="${escape(service.id)}">${service.enabled ? "Pause monitoring" : "Resume monitoring"}</button><button class="button secondary" data-edit="${escape(service.id)}">Edit service</button><button class="button danger" data-delete="${escape(service.id)}">Delete</button></div><section class="stats">${stat("Last result", badge(service.status), escape(age(service.last_checked_at)), "pulse")}${stat("Observed success", percentage(summary.success_percentage), `${summary.successes + summary.failures} valid checks`, "arrow")}${stat("Last response", service.last_status_code === null ? "—" : duration(service.last_duration_seconds), "Time to response headers", "clock")}${stat("Consecutive failures", service.consecutive_failures, `Incident threshold: ${service.failure_threshold}`, "flag", service.consecutive_failures ? "attention" : "")}</section><div class="two-columns"><section class="panel"><div class="panel-header"><div><h2>Response time</h2><p>Actual observations from this service.</p></div></div><div class="panel-body">${chart(checks, service)}</div></section><section class="panel"><div class="panel-header"><h2>Observation coverage</h2></div><div class="panel-body"><div class="key-value"><span>Valid checks</span><strong>${summary.successes + summary.failures}</strong></div><div class="key-value"><span>Blocked checks</span><strong>${summary.blocked}</strong></div><div class="key-value"><span>First in window</span><strong>${escape(date(summary.first_observation_at))}</strong></div><div class="key-value"><span>Last in window</span><strong>${escape(date(summary.last_observation_at))}</strong></div>${warning}<p class="chart-caption">Observed success is successful ÷ valid retained checks, not time-based uptime.</p></div></section></div><section class="panel"><div class="panel-header"><div><h2>Check history</h2><p>${escape(service.url)}</p></div><span class="muted mono">Every ${service.check_interval_seconds}s · Timeout ${service.timeout_seconds}s</span></div>${checks.length ? `<div class="table-scroll"><table><thead><tr><th>Observed at</th><th>Outcome</th><th>HTTP status</th><th>Duration</th><th>Details</th></tr></thead><tbody>${checks.map((check) => `<tr><td>${escape(date(check.checked_at))}</td><td>${badge(check.outcome)}</td><td class="mono">${check.status_code ?? "—"}</td><td class="mono">${check.outcome === "blocked" ? "—" : duration(check.duration_seconds)}</td><td>${escape(check.reason || "Matched expected status")}</td></tr>`).join("")}</tbody></table></div>` : empty("No check history yet", "The first observation will appear after monitoring runs.")}<div class="panel-footer"><span>Retained observations, newest first.</span>${paging(checks.length, true)}</div></section>`;
}
async function incidentsView(id) {
  const rows = await api(
    `/api/v1/incidents?limit=50&offset=${state.offset}${state.incidentFilter ? "&status=" + state.incidentFilter : ""}`,
  );
  if (id !== state.renderId) return;
  $("#view").innerHTML =
    `<section class="panel"><div class="panel-header"><div><h2>Incident history</h2><p>Every recorded outage, with its recovery or closure.</p></div><label class="sr-only" for="incident-filter">Incident status</label><select id="incident-filter"><option value="">All incidents</option><option value="open" ${state.incidentFilter === "open" ? "selected" : ""}>Open</option><option value="resolved" ${state.incidentFilter === "resolved" ? "selected" : ""}>Resolved</option></select></div>${rows.length ? `<div class="table-scroll"><table><thead><tr><th>Service</th><th>Status</th><th>Opened</th><th>Closed</th><th>Reason</th></tr></thead><tbody>${rows.map((item) => `<tr><td><button class="service-link" data-service="${escape(item.service_id)}">${escape(serviceName(item.service_id))}</button></td><td>${badge(item.resolved_at ? (item.resolution === "recovered" ? "recovered" : "closed") : "open")}</td><td>${escape(date(item.opened_at))}</td><td>${escape(item.resolved_at ? date(item.resolved_at) : "Awaiting recovery")}</td><td>${escape(item.reason)}${item.resolution === "configuration_changed" ? '<span class="notification-error">Closed after a target configuration change</span>' : ""}</td></tr>`).join("")}</tbody></table></div>` : empty("No incidents to show", "An incident appears after a service reaches its failure threshold.")}<div class="panel-footer"><span>A configuration change is not a recovery.</span>${paging(rows.length)}</div></section>`;
}
async function notificationsView(id) {
  const result = await api(
    `/api/v1/notifications?limit=50&offset=${state.offset}`,
  );
  if (id !== state.renderId) return;
  const rows = result.deliveries;
  $("#view").innerHTML =
    `<section class="panel"><div class="panel-header"><div><h2>Webhook delivery</h2><p>${result.configured ? "Incident events are queued and delivered to your configured destination." : "No alert destination is connected. Monitoring continues without notifications."}</p></div>${badge(result.configured ? (result.worker_healthy ? "healthy" : "failing") : "paused")}</div><div class="panel-body"><div class="explanation"><h3>${result.configured ? "A record of every delivery" : "Connect your alert destination"}</h3><p>${result.configured ? "Outages and recoveries have stable event IDs. Temporary failures are retried; your receiver should use the event ID to suppress duplicates." : "Ask your administrator to connect a webhook destination. Credentials and destination URLs are managed outside the dashboard."}</p></div></div></section><section class="panel"><div class="panel-header"><h2>Delivery activity</h2></div>${rows.length ? `<div class="table-scroll"><table><thead><tr><th>Event</th><th>Status</th><th>Created</th><th>Attempts</th><th>Details</th><th>Action</th></tr></thead><tbody>${rows.map((item) => `<tr><td><strong>${escape(item.service_name || serviceName(item.service_id))}</strong><span class="url-label">${escape(item.event_type.replace("incident.", "").replaceAll("_", " "))}</span></td><td>${badge(item.status)}</td><td>${escape(date(item.created_at))}</td><td class="mono">${item.attempts}</td><td>${escape(item.delivered_at ? "Accepted " + date(item.delivered_at) : item.last_error || "Waiting for delivery")}${item.status === "pending" && item.attempts ? `<span class="notification-error">Retry scheduled ${escape(date(new Date(item.next_attempt_at * 1000).toISOString()))}</span>` : ""}</td><td>${item.status === "failed" && result.configured ? `<button class="button secondary" data-retry="${escape(item.event_id)}">Retry delivery</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>` : empty("No deliveries yet", "New incident events appear here when a webhook destination is configured.")}<div class="panel-footer"><span>Delivered means the destination accepted the event.</span>${paging(rows.length)}</div></section>`;
}
async function render() {
  if (!state.data || !state.session) return;
  const id = ++state.renderId;
  const selected = state.data.services.find(
    (service) => service.id === state.selected,
  );
  const titles = {
    overview: [
      "Service overview",
      "A clear view of service health and recent activity.",
    ],
    services: [
      "Your services",
      "Manage health checks and the services you look after.",
    ],
    detail: [
      selected?.name || "Service details",
      "Check history, configuration, and observation coverage.",
    ],
    incidents: [
      "Incident history",
      "Understand what failed, when it happened, and how it recovered.",
    ],
    notifications: [
      "Notifications",
      "Follow every incident event from queue to delivery.",
    ],
  };
  const [title, description] = titles[state.page];
  $("#page-title").textContent = title;
  $("#page-description").textContent = description;
  $("#breadcrumb").textContent =
    state.page === "detail"
      ? "Service details"
      : state.page[0].toUpperCase() + state.page.slice(1);
  document.title = `${title} · System Monitoring`;
  document
    .querySelectorAll(".sidebar [data-nav]")
    .forEach((button) =>
      button.setAttribute(
        "aria-current",
        button.dataset.nav ===
          (state.page === "detail" ? "services" : state.page)
          ? "page"
          : "false",
      ),
    );
  $("#view").setAttribute("aria-busy", "true");
  try {
    if (state.page === "overview")
      $("#view").innerHTML =
        overviewStats() +
        inventory() +
        `<div class="two-columns">${recentIncidents()}${guidance()}</div>`;
    if (state.page === "services") $("#view").innerHTML = inventory(true);
    if (state.page === "detail") await detailView(id);
    if (state.page === "incidents") await incidentsView(id);
    if (state.page === "notifications") await notificationsView(id);
  } catch (error) {
    if (state.session) banner(error.message);
  } finally {
    if (id === state.renderId) $("#view").setAttribute("aria-busy", "false");
  }
}
function editService(id = null) {
  const service = state.data?.services.find((item) => item.id === id);
  state.editing = service || null;
  $("#service-form").reset();
  $("#service-error").hidden = true;
  $("#service-dialog-title").textContent = service
    ? "Edit service"
    : "Add a service";
  $("#save-service").textContent = service ? "Save changes" : "Add service";
  if (service)
    Object.entries(config(service)).forEach(([key, value]) => {
      const input = $("#service-form").elements.namedItem(key);
      if (input) input.value = value;
    });
  const origins = state.data?.approved_origins || [];
  $("#origin-hint").textContent = origins.length
    ? `Approved destinations: ${origins.join(", ")}`
    : "No destinations are approved yet. Ask your administrator to approve a service origin.";
  $("#service-dialog").showModal();
}
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  $("#login-error").hidden = true;
  try {
    state.session = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("#username").value,
        password: $("#password").value,
      }),
    });
    $("#operator-name").textContent = state.session.username;
    $("#password").value = "";
    $("#login-screen").hidden = true;
    $("#workspace").hidden = false;
    await refresh();
  } catch (error) {
    $("#login-error").textContent = error.message;
    $("#login-error").hidden = false;
  } finally {
    button.disabled = false;
  }
});
$("#logout").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
    showLogin();
  } catch (error) {
    banner(error.message);
  }
});
$("#refresh").addEventListener("click", refresh);
$("#add-service").addEventListener("click", () => editService());
$("#window").addEventListener("change", (event) => {
  state.hours = Number(event.target.value);
  refresh();
});
$("#service-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#save-service");
  button.disabled = true;
  $("#service-error").hidden = true;
  const form = new FormData(event.currentTarget);
  const body = {
    name: form.get("name"),
    url: form.get("url"),
    enabled: state.editing?.enabled ?? true,
  };
  [
    "check_interval_seconds",
    "timeout_seconds",
    "failure_threshold",
    "expected_status",
  ].forEach((key) => (body[key] = Number(form.get(key))));
  try {
    await api(
      `/api/v1/services${state.editing ? "/" + encodeURIComponent(state.editing.id) : ""}`,
      { method: state.editing ? "PUT" : "POST", body: JSON.stringify(body) },
    );
    $("#service-dialog").close();
    toast(
      state.editing
        ? "Service updated."
        : "Service added. Waiting for its first observation.",
    );
    await refresh();
  } catch (error) {
    $("#service-error").textContent = error.message;
    $("#service-error").hidden = false;
  } finally {
    button.disabled = false;
  }
});
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.hasAttribute("data-close-dialog")) {
    $("#service-dialog").close();
    return;
  }
  if (button.dataset.nav) {
    navigate(button.dataset.nav);
    return;
  }
  if (button.dataset.service) {
    navigate("detail", button.dataset.service);
    return;
  }
  if (button.hasAttribute("data-add")) {
    editService();
    return;
  }
  if (button.dataset.edit) {
    editService(button.dataset.edit);
    return;
  }
  if (button.dataset.page) {
    const key = button.hasAttribute("data-detail") ? "detailOffset" : "offset";
    state[key] = Math.max(
      0,
      state[key] + (button.dataset.page === "next" ? 50 : -50),
    );
    render();
    return;
  }
  const id =
    button.dataset.check || button.dataset.pause || button.dataset.delete;
  const service = state.data?.services.find((item) => item.id === id);
  if (!id && !button.dataset.retry) return;
  button.disabled = true;
  try {
    if (button.dataset.check) {
      const result = await api(
        `/api/v1/services/${encodeURIComponent(id)}/checks`,
        { method: "POST" },
      );
      toast(`Check completed: ${result.outcome}.`);
    }
    if (button.dataset.pause) {
      await api(`/api/v1/services/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ ...config(service), enabled: !service.enabled }),
      });
      toast(
        service.enabled
          ? "Monitoring paused. History is preserved."
          : "Monitoring resumed.",
      );
    }
    if (button.dataset.delete) {
      if (
        !confirm(
          `Delete ${service.name}? Its check history and incidents will be permanently removed.`,
        )
      )
        return;
      await api(`/api/v1/services/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      state.page = "services";
      state.selected = null;
      toast("Service and its history removed.");
    }
    if (button.dataset.retry) {
      await api(
        `/api/v1/notifications/${encodeURIComponent(button.dataset.retry)}/retry`,
        { method: "POST" },
      );
      toast("Delivery queued for another attempt.");
    }
    await refresh();
  } catch (error) {
    banner(error.message);
  } finally {
    button.disabled = false;
  }
});
document.addEventListener("input", (event) => {
  if (event.target.id === "search") {
    const position = event.target.selectionStart;
    state.search = event.target.value;
    render().then(() => {
      const input = $("#search");
      input?.focus();
      input?.setSelectionRange(position, position);
    });
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "status-filter") {
    state.filter = event.target.value;
    render();
  }
  if (event.target.id === "incident-filter") {
    state.incidentFilter = event.target.value;
    state.offset = 0;
    render();
  }
});
(async () => {
  try {
    state.session = await api("/api/auth/session");
    $("#operator-name").textContent = state.session.username;
    $("#login-screen").hidden = true;
    $("#workspace").hidden = false;
    await refresh();
  } catch {
    showLogin();
  }
})();
setInterval(() => {
  if (
    !document.hidden &&
    !$("#service-dialog").open &&
    document.activeElement?.id !== "search"
  )
    refresh();
}, 5000);

document.querySelector(".sidebar .brand").addEventListener("click", (event) => {
  event.preventDefault();
  navigate("overview");
});
