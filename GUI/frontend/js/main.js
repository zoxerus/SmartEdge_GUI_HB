// frontend/js/main.js

import { connectWebSocket } from './websocket.js';
import { loadHomeView } from './views/homeView.js';
import { loadLogView } from './views/logView.js';
import { loadDBView } from './views/dbView.js';
import { loadNodeSwarmView } from './views/nodeSwarmView.js';
import { loadPerformanceView } from './views/performanceView.js';


document.addEventListener("DOMContentLoaded", () => {
  // Start WebSocket once
  connectWebSocket();

  // Load default view
  loadHomeView();

  // Navigation
  document.getElementById("btn-home").addEventListener("click", () => {
    loadHomeView();
  });

  document.getElementById("btn-logs").addEventListener("click", () => {
    loadLogView();
  });

  document.getElementById("btn-db").addEventListener("click", () => {
    loadDBView();
  });

  document.getElementById("btn-node-swarm").addEventListener("click", () => {
    loadNodeSwarmView(); // ✅ consistent style
  });

  document.getElementById("btn-performance").addEventListener("click", () => {
  loadPerformanceView();
});
});

