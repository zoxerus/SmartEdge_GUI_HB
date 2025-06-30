// Cache the last data received
let artData = null;
let swarmData = null;

// Utility function to render a table into a container
function renderTable(container, data) {
  container.innerHTML = ""; // Clear previous content

  if (!Array.isArray(data) || data.length === 0) {
    container.innerText = "No data available.";
    return;
  }

  const table = document.createElement("table");
  table.classList.add("data-table");

  // Create header
  const headerRow = document.createElement("tr");
  Object.keys(data[0]).forEach((key) => {
    const th = document.createElement("th");
    th.innerText = key;
    headerRow.appendChild(th);
  });
  table.appendChild(headerRow);

  // Create rows
  data.forEach((row) => {
    const tr = document.createElement("tr");
    Object.values(row).forEach((val) => {
      const td = document.createElement("td");
      td.innerText = val;
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });

  container.appendChild(table);
}

// Handle DB snapshot received via WebSocket
export function handleDBSnapshot(message) {
  const tableName = message.table;
  const data = message.data;

  if (!tableName || !Array.isArray(data)) {
    console.warn("[DB View] Invalid DB snapshot received:", message);
    return;
  }

  console.log(`[DB View] Received snapshot for ${tableName}`);

  // Cache it
  if (tableName === "art") artData = data;
  if (tableName === "swarm_table") swarmData = data;

  // If view is visible, render immediately
  const artTableContainer = document.getElementById("art-table");
  const swarmTableContainer = document.getElementById("swarm-table");

  if (tableName === "art" && artTableContainer) {
    renderTable(artTableContainer, artData);
  }

  if (tableName === "swarm_table" && swarmTableContainer) {
    renderTable(swarmTableContainer, swarmData);
  }
}

// Loads the DB view UI
export function loadDBView() {
  console.log("[DB View] Loading DB view...");
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("[DB View] view-container not found in DOM");
    return;
  }

  container.innerHTML = `
    <h2>Database View</h2>
    <h3>ART Table</h3>
    <div id="art-table">Loading...</div>
    <h3>Swarm Table</h3>
    <div id="swarm-table">Loading...</div>
  `;

  // Show cached data if available
  const artTableContainer = document.getElementById("art-table");
  const swarmTableContainer = document.getElementById("swarm-table");

  if (artData !== null) renderTable(artTableContainer, artData);
  if (swarmData !== null) renderTable(swarmTableContainer, swarmData);

  // Also trigger manual fetch in case WebSocket was late
  fetch("/fetch-db")
    .then((res) => res.json())
    .then((data) => console.log("[DB View] Triggered fetch-db:", data))
    .catch((err) => console.error("[DB View] Error triggering fetch-db:", err));
}
