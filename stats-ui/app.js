const summaryPriority = [
  "uptime",
  "curr_connections",
  "active_connections",
  "total_connections",
  "accepted_connections",
  "total_special_connections",
  "max_special_connections",
  "inbound_bytes",
  "outbound_bytes",
];

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const statusMeta = document.getElementById("status-meta");
const summaryCards = document.getElementById("summary-cards");
const sectionsRoot = document.getElementById("sections-root");
const metricCount = document.getElementById("metric-count");

function formatKey(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value) {
  if (typeof value === "number") {
    return new Intl.NumberFormat().format(value);
  }
  return String(value);
}

function updateStatus(ok, message, meta) {
  const statusLine = document.getElementById("status-line");
  statusLine.className = `status-line ${ok ? "status-ok" : "status-error"}`;
  statusText.textContent = message;
  statusMeta.textContent = meta;
}

function renderSummary(summary) {
  const entries = Object.entries(summary);
  entries.sort((a, b) => {
    const ai = summaryPriority.indexOf(a[0]);
    const bi = summaryPriority.indexOf(b[0]);
    const aScore = ai === -1 ? 999 : ai;
    const bScore = bi === -1 ? 999 : bi;
    return aScore - bScore || a[0].localeCompare(b[0]);
  });

  summaryCards.innerHTML = "";
  for (const [key, value] of entries.slice(0, 8)) {
    const card = document.createElement("article");
    card.className = "metric-card";
    card.innerHTML = `
      <div class="metric-label">${formatKey(key)}</div>
      <div class="metric-value">${formatValue(value)}</div>
    `;
    summaryCards.appendChild(card);
  }
}

function renderSections(sections) {
  sectionsRoot.innerHTML = "";
  let totalMetrics = 0;
  for (const section of sections) {
    const metrics = (section.metrics || []).filter(
      (metric) => metric.name && String(metric.name).trim().length > 0,
    );
    if (metrics.length === 0) {
      continue;
    }
    totalMetrics += metrics.length;

    const block = document.createElement("section");
    block.className = "section-block";
    const rows = metrics
      .map(
        (metric) => `
          <tr>
            <td>${formatKey(metric.name)}</td>
            <td>${formatValue(metric.value ?? metric.display ?? "")}</td>
          </tr>
        `,
      )
      .join("");

    block.innerHTML = `
      <div class="section-head">
        <h3 class="section-title">${section.title || formatKey(section.name || "Section")}</h3>
        <span class="section-count">${metrics.length} metrics</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
    sectionsRoot.appendChild(block);
  }
  metricCount.textContent = `${totalMetrics} rows`;
}

async function refresh() {
  try {
    const response = await fetch("/api/stats", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Stats endpoint returned an error");
    }

    renderSummary(data.summary || {});
    renderSections(data.sections || []);

    const fetchedAt = new Date((data.fetched_at || 0) * 1000);
    updateStatus(
      true,
      "Live",
      `Updated ${fetchedAt.toLocaleTimeString()} · ${data.response_ms} ms · ${data.upstream}`,
    );
  } catch (error) {
    updateStatus(false, "Unavailable", String(error));
    summaryCards.innerHTML = "";
    sectionsRoot.innerHTML = "";
    metricCount.textContent = "0 rows";
  }
}

refresh();
setInterval(refresh, 3000);
