// frontend/js/views/logView.js

let coordinatorLogs = [];
let apLogs = [];

let hasReceivedCoordinatorLog = false;
let hasReceivedAPLog = false;

// State management utilities
function getButtonState(key) {
  const savedState = localStorage.getItem(key);
  return savedState ? JSON.parse(savedState) : false;
}

function setButtonState(key, state) {
  localStorage.setItem(key, JSON.stringify(state));
}

function toggleButtons(startBtnId, stopBtnId, isRunning) {
  const startBtn = document.getElementById(startBtnId);
  const stopBtn = document.getElementById(stopBtnId);
  
  startBtn.disabled = isRunning;
  stopBtn.disabled = !isRunning;
  
  // Update button texts based on the button IDs
  if (startBtn) {
    const startText = startBtn.id.includes('coordinator') ? 'Start Coordinator' : 'Start Access Point';
    startBtn.innerHTML = `<span class="button-text">${startText}</span>`;
  }
  if (stopBtn) {
    const stopText = stopBtn.id.includes('coordinator') ? 'Stop Coordinator' : 'Stop Access Point';
    stopBtn.innerHTML = `<span class="button-text">${stopText}</span>`;
  }
}

function setButtonLoading(button, isLoading) {
  if (!button) return;
  
  if (isLoading) {
    button.disabled = true;
    button.innerHTML = '<span class="spinner"></span><span class="button-text">Processing...</span>';
  } else {
    const buttonText = button.id.includes('start') ? 
      (button.id.includes('coordinator') ? 'Start Coordinator' : 'Start Access Point') :
      (button.id.includes('coordinator') ? 'Stop Coordinator' : 'Stop Access Point');
    button.innerHTML = `<span class="button-text">${buttonText}</span>`;
    button.disabled = false;
  }
}

export function loadLogView() {
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("[LogView] view-container not found");
    return;
  }

  container.innerHTML = `
    <div class="log-section">
      <h2>Swarm Coordinator</h2>
      <div class="log-toolbar-split">
        <div class="toolbar-group left-group">
          <button id="start-coordinator" class="start-button">
            <span class="button-text">Start Coordinator</span>
          </button>
          <button id="stop-coordinator" class="stop-button">
            <span class="button-text">Stop Coordinator</span>
          </button>
        </div>
        <div class="toolbar-group right-group">
          <button id="download-coordinator-log" class="action-button">
            <span class="button-text">Download</span>
          </button>
          <button id="clear-coordinator-log" class="action-button delete">
            <span class="button-text">Delete</span>
          </button>
        </div>
      </div>
      <div id="coordinator-logs" class="log-box">
        ${coordinatorLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
      </div>
    </div>

    <div class="log-section">
      <h2>Access Point "AP02"</h2>
      <div class="log-toolbar-split">
        <div class="toolbar-group left-group">
          <button id="start-ap" class="start-button">
            <span class="button-text">Start Access Point</span>
          </button>
          <button id="stop-ap" class="stop-button">
            <span class="button-text">Stop Access Point</span>
          </button>
        </div>
        <div class="toolbar-group right-group">
          <button id="download-ap-log" class="action-button">
            <span class="button-text">Download</span>
          </button>
          <button id="clear-ap-log" class="action-button delete">
            <span class="button-text">Delete</span>
          </button>
        </div>
      </div>
      <div id="ap-logs" class="log-box">
        ${apLogs.length === 0 ? '<span class="placeholder">Waiting for logs...</span>' : ''}
      </div>
    </div>
  `;

  // Initialize button states
  const isCoordinatorRunning = getButtonState('coordinatorRunning');
  const isAPRunning = getButtonState('apRunning');
  
  toggleButtons('start-coordinator', 'stop-coordinator', isCoordinatorRunning);
  toggleButtons('start-ap', 'stop-ap', isAPRunning);

  // === Coordinator Buttons ===
  document.getElementById('start-coordinator').addEventListener('click', () => {
    const startBtn = document.getElementById('start-coordinator');
    setButtonLoading(startBtn, true);
    
    fetch("/start/coordinator", { method: "POST" })
      .then(res => {
        if (res.ok) {
          alert("✅ Coordinator started");
          setButtonState('coordinatorRunning', true);
          toggleButtons('start-coordinator', 'stop-coordinator', true);
        } else {
          alert("❌ Failed to start Coordinator");
        }
      })
      .catch(err => {
        alert("❌ Error: " + err);
      })
      .finally(() => {
        setButtonLoading(startBtn, false);
        toggleButtons('start-coordinator', 'stop-coordinator', getButtonState('coordinatorRunning'));
      });
  });

  document.getElementById('stop-coordinator').addEventListener('click', () => {
    const confirmed = confirm("Stop Coordinator?");
    if (!confirmed) return;
    const stopBtn = document.getElementById('stop-coordinator');
    setButtonLoading(stopBtn, true);
    
    fetch("/stop/coordinator", { method: "POST" })
      .then(res => res.json())
      .then(data => {
        if (data.message) {
          alert("🛑 " + data.message);
          setButtonState('coordinatorRunning', false);
          toggleButtons('start-coordinator', 'stop-coordinator', false);
        } else {
          alert("⚠️ " + (data.error || "Unknown error"));
        }
      })
      .catch(err => {
        alert("❌ Failed to stop Coordinator: " + err.message);
      })
      .finally(() => {
        setButtonLoading(stopBtn, false);
        toggleButtons('start-coordinator', 'stop-coordinator', getButtonState('coordinatorRunning'));
      });
  });

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

  // === Access Point Buttons ===
  document.getElementById('start-ap').addEventListener('click', () => {
    const startBtn = document.getElementById('start-ap');
    setButtonLoading(startBtn, true);
    
    fetch('/start/ap', { method: 'POST' })
      .then(res => {
        if (res.ok) {
          alert("✅ Access Point started");
          setButtonState('apRunning', true);
          toggleButtons('start-ap', 'stop-ap', true);
        } else {
          alert("❌ Failed to start Access Point");
        }
      })
      .catch(err => {
        alert("❌ Error: " + err);
      })
      .finally(() => {
        setButtonLoading(startBtn, false);
        toggleButtons('start-ap', 'stop-ap', getButtonState('apRunning'));
      });
  });

  document.getElementById('stop-ap').addEventListener('click', () => {
    const confirmed = confirm("Stop Access Point?");
    if (!confirmed) return;

    const stopBtn = document.getElementById('stop-ap');
    setButtonLoading(stopBtn, true);
    
    fetch('/stop/ap', { method: 'POST' })
      .then(res => {
        if (res.ok) {
          alert("🛑 Access Point stopped");
          setButtonState('apRunning', false);
          toggleButtons('start-ap', 'stop-ap', false);
        } else {
          alert("❌ Failed to stop Access Point");
        }
      })
      .catch(err => {
        alert("❌ Error: " + err);
      })
      .finally(() => {
        setButtonLoading(stopBtn, false);
        toggleButtons('start-ap', 'stop-ap', getButtonState('apRunning'));
      });
  });

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

  // === Re-render logs ===
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

export function appendCoordinatorLog(msgObj) {
  const formatted = `[${msgObj.source}] ${msgObj.message}`;
  coordinatorLogs.push(formatted);

  const logBox = document.getElementById("coordinator-logs");
  if (logBox) {
    if (!hasReceivedCoordinatorLog) {
      logBox.innerHTML = "";
      hasReceivedCoordinatorLog = true;
    }

    const div = document.createElement("div");
    div.innerText = formatted;
    logBox.appendChild(div);
    logBox.scrollTop = logBox.scrollHeight;
  }
}

export function appendAPLog(msgObj) {
  const formatted = `[${msgObj.source}] ${msgObj.message}`;
  apLogs.push(formatted);

  const logBox = document.getElementById("ap-logs");
  if (logBox) {
    if (!hasReceivedAPLog) {
      logBox.innerHTML = "";
      hasReceivedAPLog = true;
    }

    const div = document.createElement("div");
    div.innerText = formatted;
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