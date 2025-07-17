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
    <div class="log-toolbar">
      <button id="download-coordinator-log">Download</button>
      <button id="clear-coordinator-log">Delete</button>
    </div>
    <div id="coordinator-logs" class="log-box">
      ${coordinatorLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
    </div>

    <h2>Access Point Logs</h2>
    <div class="log-toolbar">
      <button id="download-ap-log">Download</button>
      <button id="clear-ap-log">Delete</button>
    </div>
    <div id="ap-logs" class="log-box">
      ${apLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
    </div>
  `;
  // Coordinator buttons
  document.getElementById('download-coordinator-log').addEventListener('click', () => {
    const text = coordinatorLogs.join('\n');
    downloadTextAsFile(text, 'coordinator_logs.log');
  });

  document.getElementById('clear-coordinator-log').addEventListener('click', () => {
    coordinatorLogs = [];
    const box = document.getElementById("coordinator-logs");
    box.innerHTML = '<span class="placeholder">Waiting for logs...</span>';
    hasReceivedCoordinatorLog = false;
  });

  // AP buttons
  document.getElementById('download-ap-log').addEventListener('click', () => {
    const text = apLogs.join('\n');
    downloadTextAsFile(text, 'ap_logs.log');
  });

  document.getElementById('clear-ap-log').addEventListener('click', () => {
    apLogs = [];
    const box = document.getElementById("ap-logs");
    box.innerHTML = '<span class="placeholder">Waiting for logs...</span>';
    hasReceivedAPLog = false;
  });



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

function downloadTextAsFile(text, filename) {
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
