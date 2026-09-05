const API_BASE = "http://127.0.0.1:5000";

let mode = "nl"; // "nl" or "sql"

const modeNlBtn = document.getElementById("mode-nl");
const modeSqlBtn = document.getElementById("mode-sql");
const queryInput = document.getElementById("query-input");
const runBtn = document.getElementById("run-btn");
const statusDiv = document.getElementById("status");
const generatedSqlDiv = document.getElementById("generated-sql");
const resultsContainer = document.getElementById("results-container");

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

runBtn.addEventListener("click", runQuery);
queryInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    runQuery();
  }
});

async function runQuery() {
  const query = queryInput.value.trim();
  if (!query) return;

  setStatus("Running...", "");
  generatedSqlDiv.textContent = "";
  resultsContainer.innerHTML = "";

  const endpoint = mode === "nl" ? "/query/nl" : "/query/sql";

  try {
    const response = await fetch(API_BASE + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    const data = await response.json();

    if (!response.ok) {
      setStatus(data.error || "Something went wrong", "error");
      return;
    }

    if (data.sql) {
      generatedSqlDiv.textContent = `Generated SQL: ${data.sql}`;
    }

    if (data.rows) {
      setStatus(`${data.row_count} row(s) returned`, "success");
      renderTable(data.columns, data.rows);
    } else if (data.affected_rows !== undefined) {
      setStatus(`${data.affected_rows} row(s) affected`, "success");
      resultsContainer.innerHTML = `<p class="placeholder">Query executed successfully.</p>`;
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
  if (rows.length === 0) {
    resultsContainer.innerHTML = `<p class="placeholder">No results found.</p>`;
    return;
  }

  let html = "<table><thead><tr>";
  columns.forEach((col) => (html += `<th>${col}</th>`));
  html += "</tr></thead><tbody>";

  rows.forEach((row) => {
    html += "<tr>";
    columns.forEach((col) => (html += `<td>${row[col]}</td>`));
    html += "</tr>";
  });

  html += "</tbody></table>";
  resultsContainer.innerHTML = html;
}