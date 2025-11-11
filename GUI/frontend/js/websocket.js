// frontend/js/websocket.js

import { handleDBSnapshot } from './views/dbView.js';
import { appendCoordinatorLog, appendAPLog } from './views/logView.js';
import { appendPerformanceLog } from './views/performanceView.js';
import { appendHeartbeatLog } from './views/heartbeatView.js';
// If you have a snapshot handler in heartbeatView.js, import it; otherwise leave commented.
// import { handleHeartbeatSnapshot } from './views/heartbeatView.js';

export function connectWebSocket() {
  // === DB WebSocket ===
  const dbSocket = new WebSocket(`ws://${window.location.host}/ws/db`);

  dbSocket.onopen = () => console.log("[Frontend] Connected to /ws/db");

  dbSocket.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (e) {
      console.warn("[Frontend] Non-JSON DB message:", event.data);
      return;
    }

    // Backend broadcasts: { type: "db_snapshot", table: "art"|"swarm_table", data: [...] }
    if (message.type === "db_snapshot") {
      console.log("[Frontend] DB snapshot:", message.table, message);
      handleDBSnapshot(message);

      // Optional: also route swarm_table snapshots to heartbeat view
      if (message.table === "swarm_table") {
        console.log("[Frontend] Heartbeat snapshot received for swarm_table");
        // If you have a handler, uncomment next line:
        // handleHeartbeatSnapshot(message);
      }
    }
  };

  // === Logs WebSocket ===
  const logSocket = new WebSocket(`ws://${window.location.host}/ws/logs`);

  logSocket.onopen = () => {
    console.log("[Frontend] Connected to /ws/logs");

    // Subscribe to Console logs (Coordinator + AP)
    logSocket.send(JSON.stringify({
      subscribe: { type: "Console", source: null }
    }));

    // Subscribe to Metric logs (Performance)
    logSocket.send(JSON.stringify({
      subscribe: { type: "Metric", source: null }
    }));
  };

  logSocket.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (e) {
      console.warn("[Frontend] Non-JSON Log message:", event.data);
      return;
    }

    if (message.type === "log") {
      if (message.log_type === "Metric") {
        appendPerformanceLog(message);
      } else if (message.log_type === "Console") {
        const normalizedSource = String(message.source || "").toUpperCase();
        if (normalizedSource.includes("COORDINATOR")) {
          appendCoordinatorLog(message);
          appendHeartbeatLog(message); // forward to heartbeat console
        } else if (normalizedSource.includes("ACCESS POINT") || normalizedSource.includes("AP")) {
          appendAPLog(message);
        }
      }
    }
  };
}
