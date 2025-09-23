// frontend/js/websocket.js

import { handleDBSnapshot } from './views/dbView.js';
import { appendCoordinatorLog, appendAPLog } from './views/logView.js';
import { appendPerformanceLog } from './views/performanceView.js';
import { appendHeartbeatLog } from "./views/heartbeatView.js";
export function connectWebSocket() {
  // === DB WebSocket ===
  const dbSocket = new WebSocket(`ws://${window.location.host}/ws/db`);
  dbSocket.onmessage = function (event) {
    const message = JSON.parse(event.data);

    if (message.type === "db") {
      // Route to DB view
      handleDBSnapshot(message);

      // Route to Heartbeat view if keyspace matches
      if (message.table === "db" && message.table === "swarm_table") {
        console.log("[Frontend] Heartbeat snapshot received:", message.table);
        handleHeartbeatSnapshot(message);
      }
    }
  };
  dbSocket.onopen = () => console.log("[Frontend] Connected to /ws/db");

  // === Logs WebSocket ===
  const logSocket = new WebSocket(`ws://${window.location.host}/ws/logs`);
  logSocket.onmessage = function (event) {
    const message = JSON.parse(event.data);

    if (message.type === "log") {
      if (message.log_type === "Metric") {
        console.log("[Frontend] Appending performance log:", message);
        appendPerformanceLog(message);

      } else if (message.log_type === "Console") {
        // Normalize source name
        const normalizedSource = message.source.toUpperCase();

        if (normalizedSource.includes("COORDINATOR")) {
          console.log("[Frontend] Appending coordinator log:", message);
          appendCoordinatorLog(message);

          // Also forward to Heartbeat view console if a node is selected
          appendHeartbeatLog(message);

        } else if (normalizedSource.includes("ACCESS POINT") || normalizedSource.includes("AP")) {
          console.log("[Frontend] Appending AP log:", message);
          appendAPLog(message);
        }
      }
    }
  };

  logSocket.onopen = () => {
    console.log("[Frontend] Connected to /ws/logs");

    // ✅ Subscribe to Console logs (Coordinator + AP)
    logSocket.send(JSON.stringify({
      subscribe: {
        type: "Console",
        source: null  // null = all sources
      }
    }));

    // ✅ Subscribe to Metric logs (Performance)
    logSocket.send(JSON.stringify({
      subscribe: {
        type: "Metric",
        source: null
      }
    }));
  };
}
