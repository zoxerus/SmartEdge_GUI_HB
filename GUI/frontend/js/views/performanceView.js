// frontend/js/views/performanceView.js

let coordinatorPerfLogs = [];
let apPerfLogs = [];

let hasCoordinatorPerfLog = false;
let hasAPPerfLog = false;

export function loadPerformanceView() {
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("[PerformanceView] view-container not found");
    return;
  }

  container.innerHTML = `
    <h2>Coordinator Performance Logs</h2>
    <div class="log-toolbar">
      <button id="download-coordinator-perf">Download</button>
      <button id="clear-coordinator-perf">Delete</button>
    </div>
    <div id="coordinator-perf-logs" class="log-box">
      ${coordinatorPerfLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
    </div>

    <h2>Access Point Performance Logs</h2>
    <div class="log-toolbar">
      <button id="download-ap-perf">Download</button>
      <button id="clear-ap-perf">Delete</button>
    </div>
    <div id="ap-perf-logs" class="log-box">
      ${apPerfLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
    </div>
  `;

    // === Toolbar Buttons ===

  // COORDINATOR PERFORMANCE
  document.getElementById('download-coordinator-perf').addEventListener('click', () => {
    const text = coordinatorPerfLogs.join('\n');
    downloadTextAsFile(text, 'coordinator_performance.log');
  });

  document.getElementById('clear-coordinator-perf').addEventListener('click', () => {
    coordinatorPerfLogs = [];
    hasCoordinatorPerfLog = false;
    document.getElementById("coordinator-perf-logs").innerHTML = '<span class="placeholder">Waiting for logs...</span>';
  });

  // ACCESS POINT PERFORMANCE
  document.getElementById('download-ap-perf').addEventListener('click', () => {
    const text = apPerfLogs.join('\n');
    downloadTextAsFile(text, 'ap_performance.log');
  });

  document.getElementById('clear-ap-perf').addEventListener('click', () => {
    apPerfLogs = [];
    hasAPPerfLog = false;
    document.getElementById("ap-perf-logs").innerHTML = '<span class="placeholder">Waiting for logs...</span>';
  });



  // Render Coordinator logs
  if (coordinatorPerfLogs.length > 0) {
    const logBox = document.getElementById("coordinator-perf-logs");
    logBox.innerHTML = "";
    coordinatorPerfLogs.forEach((msg) => {
      const div = document.createElement("div");
      div.innerText = msg;
      logBox.appendChild(div);
    });
    hasCoordinatorPerfLog = true;
  }

  // Render AP logs
  if (apPerfLogs.length > 0) {
    const logBox = document.getElementById("ap-perf-logs");
    logBox.innerHTML = "";
    apPerfLogs.forEach((msg) => {
      const div = document.createElement("div");
      div.innerText = msg;
      logBox.appendChild(div);
    });
    hasAPPerfLog = true;
  }
}

export function appendPerformanceLog(msg) {
  if (msg.includes("[Coordinator]")) {
    coordinatorPerfLogs.push(msg);
    const logBox = document.getElementById("coordinator-perf-logs");
    if (logBox) {
      if (!hasCoordinatorPerfLog) {
        logBox.innerHTML = "";
        hasCoordinatorPerfLog = true;
      }
      const div = document.createElement("div");
      div.innerText = msg;
      logBox.appendChild(div);
      logBox.scrollTop = logBox.scrollHeight;
    }
  } else if (msg.includes("[Access Point]")) {
    apPerfLogs.push(msg);
    const logBox = document.getElementById("ap-perf-logs");
    if (logBox) {
      if (!hasAPPerfLog) {
        logBox.innerHTML = "";
        hasAPPerfLog = true;
      }
      const div = document.createElement("div");
      div.innerText = msg;
      logBox.appendChild(div);
      logBox.scrollTop = logBox.scrollHeight;
    }
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
