
let hbWS = null;
let hbWSAttempts = 0;

// ------------------ API REQUEST HELPER ------------------
async function apiRequest(path, options = {}) {
  try {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options
    });
    if (!res.ok) {
      throw new Error(`API request failed: ${res.status} ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    console.error("apiRequest error:", err);
    throw err;
  }
}


export function loadHeartbeatView() {
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("HeartbeatView: #view-container not found");
    return;
  }

  container.innerHTML = `
    <style>
      .section-title {
        font-weight: bold;
        margin-bottom: 10px;
      }
      .swarm-section, .heartbeat-section {
        border: 1px solid #ccc;
        padding: 15px;
        margin-bottom: 15px;
        background: #f4f4f4;
      }
      .button-row { margin-bottom: 10px; }
      .btn-primary {
        background-color: #4a90e2;
        color: #fff;
        border: none;
        padding: 10px 18px;
        margin-right: 6px;
        border-radius: 4px;
        cursor: pointer;
      }
      .btn-primary:hover { background-color: #357ab8; }

      /* --- Layout fix: make columns 30% / 70% and close together --- */
      .node-container {
        display: flex;
        align-items: stretch;
        gap: 8px;                 /* tighter spacing between columns */
      }
      .node-list-box {
        flex: 0 0 30%;            /* left column ~30% */
        min-width: 220px;         /* prevents collapsing */
      }
      .node-list-box select {
        width: 100%;              /* select fills the column */
        height: 280px;
        display: block;
        box-sizing: border-box;
        font-size: 19px;
        padding: 7px;
      }
      .node-details {
        flex: 1;                  /* right column takes the rest (~70%) */
        background: #fff;
        border: 1px solid #ddd;
        padding: 12px;
        box-sizing: border-box;
        min-width: 0;             /* allow proper flex shrink */
      }
      .node-details h3 {
        margin: 0 0 10px 0;
      }

      .heartbeat-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .console-box {
        background: #000;
        color: #32cd32;           /* readable green */
        padding: 10px;
        height: 280px;
        overflow-y: auto;
        font-family: monospace;
        border: 1px solid #444;
        box-sizing: border-box;
      }
    </style>

    <div class="swarm-section">
      <h2 class="section-title">Swarm Nodes</h2>
      <div class="button-row">
        <button id="btnLoadSwarm" class="btn-primary">Load Swarm Nodes</button>
        <button id="btnShowHB" class="btn-primary">Show Heartbeats</button>
      </div>

      <div class="node-container">
        <div class="node-list-box">
          <select id="nodeList" size="12"></select>
        </div>
        <div class="node-details">
          <h3>Node Details</h3>
          <p><b>UUID:</b> <span id="nodeUuid">-</span></p>
          <p><b>Status:</b> <span id="nodeStatus">-</span></p>
          <p><b>Swarm:</b> <span id="nodeSwarm">-</span></p>
          <p><b>Virt IP:</b> <span id="nodeVirtIp">-</span></p>
          <p><b>Virt MAC:</b> <span id="nodeVirtMac">-</span></p>
          <p><b>Public Key:</b> <span id="nodeKey">-</span></p>
          <p><b>Last Heartbeat:</b> <span id="nodeLastTs">-</span></p>
        </div>
      </div>
    </div>

    <div class="heartbeat-section">
      <div class="heartbeat-header">
        <h3 class="section-title">Heartbeat Logs</h3>
        <div class="button-row" style="margin-bottom:0;">
          <button id="btnDownloadHB" class="btn-primary">Download</button>
          <button id="btnClearHB" class="btn-primary">Clear</button>
        </div>
      </div>
      <pre id="heartbeatLogs" class="console-box">Waiting for logs...</pre>
    </div>
  `;

  document.getElementById("btnLoadSwarm").addEventListener("click", loadSwarmNodes);
  document.getElementById("btnShowHB").addEventListener("click", startHeartbeatLogStream);
  //startHeartbeatLogStream(); // Start logs as soon as view loads
  // Clear logs
  document.getElementById("btnClearHB").addEventListener("click", () => {
    const logBox = document.getElementById("heartbeatLogs");
    if (logBox) {
      logBox.textContent = "";
    }
  });

  // Download logs
  document.getElementById("btnDownloadHB").addEventListener("click", () => {
    const logBox = document.getElementById("heartbeatLogs");
    if (!logBox) return;

    const blob = new Blob([logBox.textContent], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "heartbeat_logs.txt";
    a.click();

    URL.revokeObjectURL(url);
  });

}

// ------------------ SWARM NODES ------------------

async function loadSwarmNodes() {
  const nodeList = document.getElementById("nodeList");
  try {
    const nodes = await apiRequest("/api/swarm/members"); 
    nodeList.innerHTML = "";

    if (!nodes || nodes.length === 0) {
      const o = document.createElement("option");
      o.disabled = true;
      o.textContent = "No nodes found";
      nodeList.appendChild(o);
      return;
    }

    nodes.forEach(n => {
      const opt = document.createElement("option");
      opt.value = n.uuid;
      opt.textContent = n.uuid;
      nodeList.appendChild(opt);
    });

    nodeList.addEventListener("change", e => loadNodeDetails(e.target.value));
    loadNodeDetails(nodes[0].uuid); // auto-load first node

  } catch (err) {
    console.error("Failed to load swarm nodes:", err);
  }
}

async function loadNodeDetails(uuid) {
  try {
    const node = await apiRequest(`/api/swarm/member/${encodeURIComponent(uuid)}`);
    document.getElementById("nodeUuid").textContent   = node?.uuid ?? "-";
    document.getElementById("nodeStatus").textContent = node?.status ?? "-";
    document.getElementById("nodeSwarm").textContent  = node?.swarm ?? "-";
    document.getElementById("nodeVirtIp").textContent = node?.virt_ip ?? "-";
    document.getElementById("nodeVirtMac").textContent= node?.virt_mac ?? "-";
    document.getElementById("nodeKey").textContent    = node?.public_key ?? "-";
    document.getElementById("nodeLastTs").textContent = node?.last_ts ?? "-";
  } catch (err) {
    console.error("Failed to load node details:", err);
  }
}

// ------------------ HEARTBEAT LOGS ------------------

function startHeartbeatLogStream() {
  const logBox = document.getElementById("heartbeatLogs");
  if (!logBox) {
    console.warn("HeartbeatView: #heartbeatLogs not found, aborting log stream setup");
    return;
  }

  if (hbWS) {
    try { hbWS.close(); } catch {}
    hbWS = null;
  }

  const scheme = location.protocol === "https:" ? "wss://" : "ws://";
  const url = scheme + location.host + "/ws/heartbeat_logs";

  hbWS = new WebSocket(url);

  hbWS.onopen = () => {
    hbWSAttempts = 0;
    if (logBox.textContent === "Waiting for logs...") logBox.textContent = "";
    appendHeartbeatLog("[Connected to log server, waiting for logs...]");
  };

  hbWS.onmessage = (ev) => appendHeartbeatLog(ev.data);

  hbWS.onclose = () => {
    if (document.getElementById("heartbeatLogs")) {
      appendHeartbeatLog("[Disconnected from log server]");
    }
    const delay = Math.min(10000, 1000 * Math.pow(2, hbWSAttempts++));
    setTimeout(startHeartbeatLogStream, delay);
  };

  hbWS.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}


export function appendHeartbeatLog(message) {
  const logBox = document.getElementById("heartbeatLogs");
  if (!logBox) return;
  if (logBox.textContent === "Waiting for logs...") logBox.textContent = "";
  logBox.textContent += message + "\n";
  logBox.scrollTop = logBox.scrollHeight;
}
