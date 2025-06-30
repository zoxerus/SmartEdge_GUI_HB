// frontend/js/websocket.js

import { handleDBSnapshot } from './views/dbView.js';
import { appendCoordinatorLog, appendAPLog } from './views/logView.js';

export function connectWebSocket() {
  // === DB WebSocket ===
  const dbSocket = new WebSocket(`ws://${window.location.host}/ws/db`);
  dbSocket.onmessage = function (event) {
    const message = JSON.parse(event.data);
    if (message.type === "db") {
      handleDBSnapshot(message);
    }
  };
  dbSocket.onopen = () => console.log("[Frontend] Connected to /ws/db");

  // === Logs WebSocket ===
  const logSocket = new WebSocket(`ws://${window.location.host}/ws/logs`);
  logSocket.onmessage = function (event) {
    const message = JSON.parse(event.data);
    if (message.type === "log") {
      if (message.source === "COORDINATOR") {
        console.log("[Frontend] Appending coordinator log:", message.message);
        appendCoordinatorLog(message.message);
      } else if (message.source === "AP") {
        console.log("[Frontend] Appending AP log:", message.message);
        appendAPLog(message.message);
      }
    }
  };
  logSocket.onopen = () => console.log("[Frontend] Connected to /ws/logs");
}
