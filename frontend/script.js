const API_BASE = "http://127.0.0.1:5000";

let mode = "nl"; // "nl" or "sql"

const modeNlBtn      = document.getElementById("mode-nl");
const modeSqlBtn     = document.getElementById("mode-sql");
const queryInput     = document.getElementById("query-input");
const runBtn         = document.getElementById("run-btn");
const statusDiv      = document.getElementById("status");
const generatedSqlDiv = document.getElementById("generated-sql");
const resultsContainer = document.getElementById("results-container");
const historyList    = document.getElementById("history-list");

// ── History store ────────────────────────────────────────────────────────────
// Each entry: { query, timestamp, status, statusType, sql, columns, rows, affectedRows, isError }
let history = JSON.parse(localStorage.getItem("sqlHistory2") || "[]");

// Separate array just of query strings for ↑/↓ navigation
let navIndex = -1;
let draftQuery = "";

function queryStrings() {
  return history.map(e => e.query);
}

function saveHistoryEntry(entry) {
  // Avoid saving back-to-back identical queries
  const last = history[history.length - 1];
  if (last && last.query === entry.query && last.status === entry.status) {
    // still update panel in case something changed
    renderHistoryPanel();
    return;
  }
  history.push(entry);
  // cap at 100 entries
  if (history.length > 100) history.shift();
  localStorage.setItem("sqlHistory2", JSON.stringify(history));
  navIndex = -1;
  draftQuery = "";
  renderHistoryPanel();
}

// ── Build table HTML (reusable) ───────────────────────────────────────────────
function buildTableHtml(columns, rows) {
  if (!rows || rows.length === 0) return `<p class="placeholder">No results found.</p>`;
  let html = "<table><thead><tr>";
  columns.forEach(col => (html += `<th>${escapeHtml(col)}</th>`));
  html += "</tr></thead><tbody>";
  rows.forEach(row => {
    html += "<tr>";
    columns.forEach(col => (html += `<td>${escapeHtml(String(row[col] ?? ""))}</td>`));
    html += "</tr>";
  });
  html += "</tbody></table>";
  return html;
}

// ── History panel render ─────────────────────────────────────────────────────
function renderHistoryPanel() {
  historyList.innerHTML = "";
  if (history.length === 0) {
    historyList.innerHTML = `<li class="history-empty">No history yet.</li>`;
    return;
  }

  [...history].reverse().forEach((entry, reversedIdx) => {
    const realIdx = history.length - 1 - reversedIdx; // index in original array
    const num = history.length - reversedIdx;
    const ts  = new Date(entry.timestamp).toLocaleTimeString();
    const isError = entry.isError;

    const li = document.createElement("li");
    li.className = "history-item" + (isError ? " history-error" : "");

    // ── Header row (always visible) ───────────────────────────────────────
    const header = document.createElement("div");
    header.className = "history-header-row";
    header.innerHTML = `
      <span class="history-index">${num}</span>
      <span class="history-cmd" title="Click to load">${escapeHtml(entry.query)}</span>
      <span class="history-ts">${ts}</span>
      <span class="history-badge ${isError ? "badge-error" : "badge-ok"}">${isError ? "ERR" : entry.columns ? entry.rows.length + " row" + (entry.rows.length !== 1 ? "s" : "") : entry.affectedRows !== undefined ? entry.affectedRows + " affected" : "OK"}</span>
      <button class="history-run-btn" title="Re-run">▶</button>
      <button class="history-expand-btn" title="Toggle result">▾</button>
    `;

    // ── Result body (collapsible) ─────────────────────────────────────────
    const body = document.createElement("div");
    body.className = "history-body collapsed";

    // Build body content
    let bodyHtml = "";
    if (entry.sql) {
      bodyHtml += `<div class="history-gen-sql">SQL: ${escapeHtml(entry.sql)}</div>`;
    }
    if (isError) {
      bodyHtml += `<div class="history-status-msg error-msg">${escapeHtml(entry.status)}</div>`;
    } else if (entry.columns && entry.rows) {
      bodyHtml += buildTableHtml(entry.columns, entry.rows);
    } else if (entry.affectedRows !== undefined) {
      bodyHtml += `<p class="placeholder">Query executed successfully. ${entry.affectedRows} row(s) affected.</p>`;
    } else {
      bodyHtml += `<p class="placeholder">No result data.</p>`;
    }
    body.innerHTML = bodyHtml;

    li.appendChild(header);
    li.appendChild(body);
    historyList.appendChild(li);

    // Toggle expand
    const expandBtn = header.querySelector(".history-expand-btn");
    expandBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const collapsed = body.classList.toggle("collapsed");
      expandBtn.textContent = collapsed ? "▾" : "▴";
    });

    // Load query into textarea
    header.querySelector(".history-cmd").addEventListener("click", () => {
      queryInput.value = entry.query;
      queryInput.focus();
      navIndex = -1;
    });

    // Re-run
    header.querySelector(".history-run-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      queryInput.value = entry.query;
      runQuery();
    });
  });
}

// ── Mode toggle ──────────────────────────────────────────────────────────────
modeNlBtn.addEventListener("click", () => {
  mode = "nl";
  modeNlBtn.classList.add("active");
  modeSqlBtn.classList.remove("active");
  queryInput.placeholder = "e.g. show me the top 5 students who scored above 80";
});

modeSqlBtn.addEventListener("click", () => {
  mode = "sql";
  modeSqlBtn.classList.add("active");
  modeNlBtn.classList.remove("active");
  queryInput.placeholder = "e.g. SELECT * FROM students WHERE score > 80 ORDER BY score DESC LIMIT 5;";
});

// ── Keyboard shortcuts ───────────────────────────────────────────────────────
runBtn.addEventListener("click", runQuery);

queryInput.addEventListener("keydown", (e) => {
  // Enter → submit
  if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    runQuery();
    return;
  }
  // Ctrl/Shift+Enter → new line (default behaviour)
  if (e.key === "Enter") return;

  // ↑ → go back in history
  if (e.key === "ArrowUp") {
    e.preventDefault();
    const qs = queryStrings();
    if (qs.length === 0) return;
    if (navIndex === -1) {
      draftQuery = queryInput.value;
      navIndex = qs.length - 1;
    } else if (navIndex > 0) {
      navIndex--;
    }
    queryInput.value = qs[navIndex];
    setTimeout(() => queryInput.setSelectionRange(queryInput.value.length, queryInput.value.length), 0);
    return;
  }

  // ↓ → go forward in history
  if (e.key === "ArrowDown") {
    e.preventDefault();
    if (navIndex === -1) return;
    const qs = queryStrings();
    if (navIndex < qs.length - 1) {
      navIndex++;
      queryInput.value = qs[navIndex];
    } else {
      navIndex = -1;
      queryInput.value = draftQuery;
    }
    setTimeout(() => queryInput.setSelectionRange(queryInput.value.length, queryInput.value.length), 0);
    return;
  }

  navIndex = -1; // any other key → reset nav
});

// ── Query execution ──────────────────────────────────────────────────────────
async function runQuery(confirmed = false) {
  const query = queryInput.value.trim();
  if (!query) return;

  setStatus("Running…", "");
  generatedSqlDiv.textContent = "";
  resultsContainer.innerHTML = "";

  const endpoint = mode === "nl" ? "/query/nl" : "/query/sql";

  try {
    const response = await fetch(API_BASE + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, confirmed }),
    });

    const data = await response.json();

    // ── Destructive operation: ask for confirmation before executing ──────────
    if (data.needs_confirm) {
      setStatus("⚠️ Confirmation required — nothing has been executed yet.", "warn");
      generatedSqlDiv.textContent = "";
      resultsContainer.innerHTML = `
        <div class="confirm-box">
          <div class="confirm-icon">⚠️</div>
          <div class="confirm-content">
            <p class="confirm-warning">${escapeHtml(data.warning)}</p>
            <div class="confirm-sql-label">SQL that will run:</div>
            <code class="confirm-sql">${escapeHtml(data.sql)}</code>
            <div class="confirm-actions">
              <button id="confirm-cancel-btn"  class="confirm-btn cancel-btn">Cancel</button>
              <button id="confirm-execute-btn" class="confirm-btn execute-btn">Yes, execute anyway</button>
            </div>
          </div>
        </div>`;

      document.getElementById("confirm-cancel-btn").addEventListener("click", () => {
        resultsContainer.innerHTML = `<p class="placeholder">Cancelled. Nothing was executed.</p>`;
        setStatus("", "");
      });

      document.getElementById("confirm-execute-btn").addEventListener("click", () => {
        runQuery(true);  // re-send same query with confirmed = true
      });
      return;
    }

    if (!response.ok) {
      const errMsg = data.error || "Something went wrong";
      setStatus(errMsg, "error");
      saveHistoryEntry({
        query,
        timestamp: Date.now(),
        status: errMsg,
        statusType: "error",
        isError: true,
        sql: data.sql || null,
        columns: null,
        rows: null,
        affectedRows: undefined,
      });
      return;
    }

    if (data.sql) {
      generatedSqlDiv.textContent = `Generated SQL: ${data.sql}`;
    }

    if (data.rows) {
      const msg = `${data.row_count} row(s) returned`;
      setStatus(msg, "success");
      renderTable(data.columns, data.rows);
      saveHistoryEntry({
        query,
        timestamp: Date.now(),
        status: msg,
        statusType: "success",
        isError: false,
        sql: data.sql || null,
        columns: data.columns,
        rows: data.rows,
        affectedRows: undefined,
      });
    } else if (data.affected_rows !== undefined) {
      const msg = `${data.affected_rows} row(s) affected`;
      setStatus(msg, "success");
      resultsContainer.innerHTML = `<p class="placeholder">Query executed successfully.</p>`;
      saveHistoryEntry({
        query,
        timestamp: Date.now(),
        status: msg,
        statusType: "success",
        isError: false,
        sql: data.sql || null,
        columns: null,
        rows: null,
        affectedRows: data.affected_rows,
      });
    }
  } catch (err) {
    setStatus("Could not reach the server. Is the backend running?", "error");
  }
}

function setStatus(msg, type) {
  statusDiv.textContent = msg;
  statusDiv.className = "status " + type;
}

function renderTable(columns, rows) {
  resultsContainer.innerHTML = buildTableHtml(columns, rows);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Init ─────────────────────────────────────────────────────────────────────
document.getElementById("clear-history-btn").addEventListener("click", () => {
  history = [];
  localStorage.removeItem("sqlHistory2");
  navIndex = -1;
  draftQuery = "";
  renderHistoryPanel();
});

renderHistoryPanel();