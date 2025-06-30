// frontend/js/views/logView.js

// Persistent log storage
let coordinatorLogs = [];
let apLogs = [];

// Track if we've received first logs (for placeholder behavior)
let hasReceivedCoordinatorLog = false;
let hasReceivedAPLog = false;

export function loadLogView() {
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("[LogView] view-container not found");
    return;
  }

  container.innerHTML = `
    <h2>Coordinator Logs</h2>
    <div id="coordinator-logs" class="log-box">
      ${coordinatorLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
    </div>

    <h2>Access Point Logs</h2>
    <div id="ap-logs" class="log-box">
      ${apLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
    </div>
  `;

  // Re-render existing logs if we have any
  if (coordinatorLogs.length > 0) {
    const logBox = document.getElementById("coordinator-logs");
    logBox.innerHTML = "";
    coordinatorLogs.forEach((msg) => {
      const div = document.createElement("div");
      div.innerText = msg;
      logBox.appendChild(div);
    });
    hasReceivedCoordinatorLog = true;
  }

  if (apLogs.length > 0) {
    const logBox = document.getElementById("ap-logs");
    logBox.innerHTML = "";
    apLogs.forEach((msg) => {
      const div = document.createElement("div");
      div.innerText = msg;
      logBox.appendChild(div);
    });
    hasReceivedAPLog = true;
  }
}

export function appendCoordinatorLog(msg) {
  coordinatorLogs.push(msg);

  const logBox = document.getElementById("coordinator-logs");
  if (logBox) {
    if (!hasReceivedCoordinatorLog) {
      logBox.innerHTML = ""; // Remove "Waiting for logs..."
      hasReceivedCoordinatorLog = true;
    }

    const div = document.createElement("div");
    div.innerText = msg;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
  }
}

export function appendAPLog(msg) {
  apLogs.push(msg);

  const logBox = document.getElementById("ap-logs");
  if (logBox) {
    if (!hasReceivedAPLog) {
      logBox.innerHTML = ""; // Remove "Waiting for logs..."
      hasReceivedAPLog = true;
    }

    const div = document.createElement("div");
    div.innerText = msg;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
  }
}