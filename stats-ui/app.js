const summaryPriority = [
  "uptime",
  "active_connections",
  "total_connections",
  "inbound_connections",
  "outbound_connections",
  "workers",
  "total_special_connections",
  "max_special_connections",
  "average_idle_percent",
  "load_recent_total",
];

const statusText = document.getElementById("status-text");
const statusMeta = document.getElementById("status-meta");
const summaryCards = document.getElementById("summary-cards");
const linksRoot = document.getElementById("links-root");
const linkCount = document.getElementById("link-count");
const sectionsRoot = document.getElementById("sections-root");
const metricCount = document.getElementById("metric-count");
const checkStates = new Map();
let currentLinks = [];

function formatKey(key) {
  return key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value) {
  if (typeof value === "number") {
    return new Intl.NumberFormat().format(value);
  }
  return String(value);
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
  } catch (error) {
    window.prompt("Copy link", value);
  }
}

async function checkProxy(host, port, secret) {
  const response = await fetch("/api/check-proxy", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ host, port, secret }),
  });

  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "Proxy check failed");
  }
  return data;
}

function getCheckState(key) {
  return (
    checkStates.get(key) || {
      tone: "",
      text: "Idle",
      busy: false,
    }
  );
}

function setCheckState(key, nextState) {
  const currentState = getCheckState(key);
  checkStates.set(key, { ...currentState, ...nextState });
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

function renderLinks(links) {
  currentLinks = Array.isArray(links) ? links : [];
  linksRoot.innerHTML = "";

  if (currentLinks.length === 0) {
    linkCount.textContent = "0 links";
    const empty = document.createElement("section");
    empty.className = "link-block";
    empty.innerHTML = `
      <div class="link-empty">
        Set MTPROXY_PUBLIC_HOST and SECRET to expose connection links here.
      </div>
    `;
    linksRoot.appendChild(empty);
    return;
  }

  linkCount.textContent = `${currentLinks.length * 2} links`;

  for (const link of currentLinks) {
    const standardState = getCheckState(`standard-${link.index}`);
    const paddedState = getCheckState(`padded-${link.index}`);
    const block = document.createElement("section");
    block.className = "link-block";
    block.innerHTML = `
      <div class="link-head">
        <h3 class="section-title">${link.label}</h3>
        <span class="section-count">${link.host}:${link.port}</span>
      </div>
      <div class="link-grid">
        <div class="link-row">
          <div class="link-meta">
            <span class="link-kind">Standard</span>
            <code class="link-value">${link.tg_url}</code>
            <span class="check-state ${standardState.tone}" data-check-state="standard-${link.index}">${standardState.text}</span>
          </div>
          <div class="link-actions">
            <button
              type="button"
              class="action-button"
              data-check-host="${link.host}"
              data-check-port="${link.port}"
              data-check-secret="${encodeURIComponent(link.secret)}"
              data-check-target="standard-${link.index}"
              ${standardState.busy ? "disabled" : ""}
            >Check</button>
            <button type="button" class="action-button" data-copy="${encodeURIComponent(link.tg_url)}">Copy</button>
          </div>
        </div>
        <div class="link-row">
          <div class="link-meta">
            <span class="link-kind">Padded</span>
            <code class="link-value">${link.padded_tg_url}</code>
            <span class="check-state ${paddedState.tone}" data-check-state="padded-${link.index}">${paddedState.text}</span>
          </div>
          <div class="link-actions">
            <button
              type="button"
              class="action-button"
              data-check-host="${link.host}"
              data-check-port="${link.port}"
              data-check-secret="${encodeURIComponent(link.padded_secret)}"
              data-check-target="padded-${link.index}"
              ${paddedState.busy ? "disabled" : ""}
            >Check</button>
            <button type="button" class="action-button" data-copy="${encodeURIComponent(link.padded_tg_url)}">Copy</button>
          </div>
        </div>
      </div>
    `;
    linksRoot.appendChild(block);
  }

  for (const button of linksRoot.querySelectorAll("[data-copy]")) {
    button.addEventListener("click", () => {
      copyText(decodeURIComponent(button.dataset.copy || ""));
    });
  }

  for (const button of linksRoot.querySelectorAll("[data-check-secret]")) {
    button.addEventListener("click", async () => {
      const targetKey = button.dataset.checkTarget || "";
      const host = button.dataset.checkHost || "";
      const port = Number(button.dataset.checkPort || 0);
      const secret = decodeURIComponent(button.dataset.checkSecret || "");

      if (!targetKey || !host || !port || !secret) {
        return;
      }

      setCheckState(targetKey, {
        tone: "check-pending",
        text: "Checking",
        busy: true,
      });
      renderLinks(currentLinks);

      try {
        const result = await checkProxy(host, port, secret);
        const detail = result.latency_seconds
          ? `${result.latency_seconds}s`
          : `${result.response_ms} ms`;
        setCheckState(targetKey, {
          tone: "check-ok",
          text: `OK · ${detail}`,
          busy: false,
        });
      } catch (error) {
        setCheckState(targetKey, {
          tone: "check-error",
          text: String(error),
          busy: false,
        });
      }

      renderLinks(currentLinks);
    });
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

    renderLinks(data.links || []);
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
    linksRoot.innerHTML = "";
    linkCount.textContent = "0 links";
    sectionsRoot.innerHTML = "";
    metricCount.textContent = "0 rows";
  }
}

refresh();
setInterval(refresh, 3000);
