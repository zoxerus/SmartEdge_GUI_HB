// Node–Swarm Management view (complete, updated, and self-contained)
export function loadNodeSwarmView() {
  // ---- State ----
  let selectedUuid = null;
  let selectedSwarmTable = null;
  let selectedSwarmNodeUuid = null;
  let allSwarms = [];

  // ---- Root container ----
  const container = document.getElementById("view-container");

  container.innerHTML = `
    <div id="node-swarm-view" class="node-swarm-layout">
      <!-- Left Panel -->
      <div id="art-panel" class="panel">
        <h2>ART Nodes</h2>
        <div id="node-details" class="info-box">
          <div id="art-node-list" class="list-box"></div>

          <h3>Node Details</h3>
          <p><strong>UUID:</strong> <span id="detail-uuid"></span></p>
          <p><strong>Current AP:</strong> <span id="detail-current_ap"></span></p>
          <p><strong>Swarm:</strong> <span id="detail-swarm"></span></p>
          <p><strong>Last update:</strong> <span id="detail-last_update"></span></p>
        </div>

        <!-- Join Controls -->
        <div id="join-controls" class="info-box" style="margin-top:10px;">
          <label for="swarm-select">Select Swarm:</label>
          <select id="swarm-select" disabled>
            <option value="">-- Choose a swarm --</option>
          </select>

          <div style="margin-top:6px;">
            <label for="heartbeat-select">Enable Heartbeat:</label>
            <select id="heartbeat-select" style="margin-left:6px;">
              <!-- Default OFF per requirements -->
              <option value="false" selected>Off</option>
              <option value="true">On</option>
            </select>
          </div>

          <button id="ask-join-btn" disabled class="ask-btn" style="margin-top:8px;">Ask to Join</button>

          <div id="node-log" class="node-log" style="margin-top:10px;">Waiting for logs</div>
        </div>
      </div>

      <!-- Right Panel -->
      <div id="swarm-panel" class="panel">
        <h2>Available Swarms</h2>
        <div class="info-box">
          <ul id="swarm-list" class="list-box"></ul>

          <div id="swarm-members" style="margin-top:10px;">
            <h3>Swarm Members</h3>
            <ul id="member-list" class="list-unstyled"></ul>

            <!-- Leave Action Section -->
            <div id="leave-controls" style="margin-top:10px;">
              <button id="ask-leave-btn" disabled class="ask-btn">Ask to Leave</button>
              <div id="leave-log" class="node-log" style="margin-top:10px;">Waiting for leave logs</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  // ---- Element refs ----
  const swarmSelect = document.getElementById("swarm-select");
  const hbSelect = document.getElementById("heartbeat-select");
  const askButton = document.getElementById("ask-join-btn");
  const logBox = document.getElementById("node-log");
  const leaveBtn = document.getElementById("ask-leave-btn");
  const leaveLog = document.getElementById("leave-log");

  // ---- Helpers ----
  function updateJoinButtonState() {
    askButton.disabled = !(selectedUuid && selectedSwarmTable);
  }

  function highlightSingle(selector, el) {
    document.querySelectorAll(selector).forEach(x => x.classList.remove("selected"));
    if (el) el.classList.add("selected");
  }

  // =========================================================
  // =============== Two-Step Heartbeat Modals ===============
  // =========================================================

  // Modal 1: Lost Heartbeat Limit (shown only if swarm is empty)
  let openLostLimitModal = () => {};
  let closeLostLimitModal = () => {};

  (function ensureLostLimitModal() {
    const existing = document.getElementById("lost-limit-modal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "lost-limit-modal";
    modal.style.display = "none";
    modal.innerHTML = `
      <div id="ll-overlay" style="
        position: fixed; inset: 0; background: rgba(0,0,0,0.5);
        display: flex; justify-content: center; align-items: center; z-index: 9999;">
        <div role="dialog" aria-modal="true" aria-labelledby="ll-title" style="
          background: #fff; padding: 20px; border-radius: 12px; width: 340px; max-width: 92vw;
          box-shadow: 0 10px 30px rgba(0,0,0,0.25);">
          <h3 id="ll-title" style="margin-bottom: 12px;">Set Lost Heartbeat Limit</h3>
          <p style="font-size: 13px; color: #555; margin-bottom: 8px;">
            ⚠️ This value applies to the entire swarm and can only be set once when the swarm is empty.
          </p>

          <label for="lost-limit-select" style="display:block;">Allowed Lost Heartbeats</label>
          <select id="lost-limit-select" style="width:40%; margin-bottom:10px;">
            ${Array.from({ length: 10 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("")}
          </select>

          <div style="text-align:right;">
            <button id="ll-cancel-btn" style="margin-right:8px;">Cancel</button>
            <button id="ll-confirm-btn" style="background:#007bff;color:#fff;padding:4px 10px;border-radius:4px;">Confirm</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector("#ll-overlay").addEventListener("click", (e) => {
      if (e.target.id === "ll-overlay") modal.style.display = "none";
    });
    modal.querySelector("#ll-cancel-btn").addEventListener("click", () => {
      modal.style.display = "none";
    });

    modal.querySelector("#ll-confirm-btn").addEventListener("click", async () => {
      if (!selectedUuid || !selectedSwarmTable) {
        logBox.textContent = "❌ Please select both a node and a swarm.";
        modal.style.display = "none";
        return;
      }

      const lostLimit = parseInt(document.getElementById("lost-limit-select").value, 10);
      modal.style.display = "none";

      // Start or reuse the heartbeat server with this limit (swarm-wide)
      try {
        const res = await fetch("/start-heartbeat-server", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lost_limit: lostLimit })
        });
        const result = await res.json();
        if (result.success) {
          console.log("✅ Heartbeat server:", result.output || `started (limit=${lostLimit})`);
        } else {
          console.error("❌ Failed to start heartbeat server:", result.error);
          logBox.textContent = "❌ Failed to start heartbeat server.";
        }
      } catch (err) {
        console.error("❌ Error starting heartbeat server:", err);
      }

      // Proceed to the heartbeat parameters modal
      openHeartbeatParamsModal();
    });

    openLostLimitModal = () => { modal.style.display = "flex"; };
    closeLostLimitModal = () => { modal.style.display = "none"; };
  })();

  // Modal 2: Heartbeat parameters (chain length, window, interval)
  let openHeartbeatParamsModal = () => {};
  let closeHeartbeatParamsModal = () => {};

  (function ensureHeartbeatParamsModal() {
    const existing = document.getElementById("hb-param-modal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "hb-param-modal";
    modal.style.display = "none";
    modal.innerHTML = `
      <div id="hb-overlay-param" style="
        position: fixed; inset: 0; background: rgba(0,0,0,0.5);
        display: flex; justify-content: center; align-items: center; z-index: 9999;">
        <div role="dialog" aria-modal="true" aria-labelledby="hb-param-title" style="
          background: #fff; padding: 20px; border-radius: 12px; width: 360px; max-width: 92vw;
          box-shadow: 0 10px 30px rgba(0,0,0,0.25);">
          <h3 id="hb-param-title" style="margin-bottom: 12px;">Heartbeat Parameters</h3>

          <label for="hb-length" style="display:block;">Chain Length</label>
          <select id="hb-length" style="width:50%; margin-bottom:8px;">
            ${[100, 500, 1000, 1500, 2000].map(v => `<option value="${v}">${v}</option>`).join("")}
          </select>
          <small style="display:block;margin-bottom:12px;color:#555;">Total number of hash points in the Winternitz chain.</small>

          <label for="hb-window" style="display:block;">Window</label>
          <select id="hb-window" style="width:50%; margin-bottom:8px;">
            ${[2, 3, 4, 5].map(v => `<option value="${v}">${v}</option>`).join("")}
          </select>
          <small style="display:block;margin-bottom:12px;color:#555;">Verifier acceptance window for out-of-order or delayed heartbeats.</small>

          <label for="hb-interval" style="display:block;">Interval</label>
          <select id="hb-interval" style="width:50%; margin-bottom:8px;">
            ${Array.from({ length: 10 }, (_, i) => `<option value="${i + 1}">${i + 1}s</option>`).join("")}
          </select>
          <small style="display:block;margin-bottom:12px;color:#555;">Seconds between heartbeats sent by the node.</small>

          <div style="text-align:right;margin-top:8px;">
            <button id="hb-cancel-btn2" style="margin-right:8px;">Cancel</button>
            <button id="hb-confirm-btn2" style="background:#007bff;color:#fff;padding:4px 10px;border-radius:4px;">Confirm & Send</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector("#hb-overlay-param").addEventListener("click", (e) => {
      if (e.target.id === "hb-overlay-param") modal.style.display = "none";
    });
    modal.querySelector("#hb-cancel-btn2").addEventListener("click", () => {
      modal.style.display = "none";
    });

    modal.querySelector("#hb-confirm-btn2").addEventListener("click", () => {
      if (!selectedUuid || !selectedSwarmTable) {
        logBox.textContent = "❌ Please select both a node and a swarm.";
        modal.style.display = "none";
        return;
      }

      const length = parseInt(document.getElementById("hb-length").value, 10);
      const windowSize = parseInt(document.getElementById("hb-window").value, 10);
      const interval = parseInt(document.getElementById("hb-interval").value, 10);

      modal.style.display = "none";

      // Send the normal join request with heartbeat enabled
      sendJoinRequest({
        uuid: selectedUuid,
        swarm: selectedSwarmTable,
        heartbeat: true,
        hb_length: length,
        hb_window: windowSize,
        hb_interval: interval
      });
    });

    openHeartbeatParamsModal = () => { modal.style.display = "flex"; };
    closeHeartbeatParamsModal = () => { modal.style.display = "none"; };
  })();

  // ---- Ask to Join ----
  askButton.addEventListener("click", async () => {
    if (!selectedUuid || !selectedSwarmTable) {
      logBox.textContent = "❌ Please select both a node and a swarm.";
      return;
    }

    const heartbeatEnabled = hbSelect.value === "true";
    if (heartbeatEnabled) {
      // Before showing any modal, check if swarm is empty
      try {
        const res = await fetch(`/api/swarm/${selectedSwarmTable}/is-empty`);
        const data = await res.json();

        if (data && data.empty === true) {
          // Swarm empty → first-time setup modal for lost limit
          openLostLimitModal();
        } else {
          // Swarm not empty → skip to heartbeat params modal
          openHeartbeatParamsModal();
        }
        return;
      } catch (err) {
        console.error("Failed to check swarm emptiness:", err);
        // Fallback: open HB params modal to avoid blocking user
        openHeartbeatParamsModal();
        return;
      }
    }

    // Heartbeat OFF → send immediately
    sendJoinRequest({
      uuid: selectedUuid,
      swarm: selectedSwarmTable,
      heartbeat: false
    });
  });

  // ---- Join request sender (shared) ----
  function sendJoinRequest(payload) {
    logBox.textContent = `⏳ Sending join request for ${payload.uuid} to swarm "${payload.swarm}"...`;
    fetch("/request-join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(res => res.json())
      .then(result => {
        if (result && result.success) {
          logBox.textContent = result.output || "✅ Join request sent.";
        } else {
          logBox.textContent = "❌ Error: " + (result?.error || "Unknown error");
        }
      })
      .catch(err => {
        logBox.textContent = "❌ Request failed: " + err.message;
      });
  }

  // ---- Populate ART Nodes ----
  fetch("/art-nodes")
    .then(res => res.json())
    .then(data => {
      const nodes = Array.isArray(data) ? data : (data.nodes || []);
      const list = document.getElementById("art-node-list");
      list.innerHTML = "";

      nodes.forEach(node => {
        const div = document.createElement("div");
        div.textContent = node.uuid;
        div.className = "art-node-item";
        div.style.cursor = "pointer";
        div.style.padding = "4px";
        div.style.borderBottom = "1px solid #ccc";

        div.addEventListener("click", () => {
          // highlight & update details
          document.querySelectorAll(".art-node-item").forEach(x => x.classList.remove("selected"));
          div.classList.add("selected");

          selectedUuid = node.uuid;
          selectedSwarmTable = null;
          askButton.disabled = true;
          swarmSelect.disabled = false;
          hbSelect.value = "false";

          document.getElementById("detail-uuid").textContent = node.uuid || "-";
          document.getElementById("detail-current_ap").textContent = node.current_ap || "-";
          document.getElementById("detail-swarm").textContent = node.swarm_id || "-";
          document.getElementById("detail-last_update").textContent = node.last_update || "-";

          swarmSelect.innerHTML = '<option value="">-- Choose a swarm --</option>';
          allSwarms.forEach(swarm => {
            const opt = document.createElement("option");
            opt.value = swarm.table;
            opt.textContent = swarm.name;
            swarmSelect.appendChild(opt);
          });
          logBox.textContent = "Node selected. Choose a swarm and click Ask to Join.";
        });

        list.appendChild(div);
      });
    })
    .catch(err => {
      console.error("Failed to fetch ART nodes:", err);
    });

  // ---- Populate Available Swarms list (right panel) ----
  fetch("/swarms")
    .then(res => res.json())
    .then(swarms => {
      allSwarms = Array.isArray(swarms) ? swarms : [];
      const list = document.getElementById("swarm-list");
      list.innerHTML = "";

      if (!Array.isArray(swarms)) throw new Error("Invalid response format for swarms");

      swarms.forEach((swarm) => {
        const li = document.createElement("li");
        li.textContent = swarm.name;
        li.style.cursor = "pointer";
        li.style.padding = "4px";
        li.style.borderBottom = "1px solid #ccc";

        li.addEventListener("click", () => {
          highlightSingle("#swarm-list li", li);

          // Set currently selected swarm table (enables Ask to Join if node is chosen)
          selectedSwarmTable = swarm.table;
          updateJoinButtonState();

          // Load members for this swarm
          fetch(`/swarms/${swarm.table}`)
            .then(res => res.json())
            .then(members => {
              const memberList = document.getElementById("member-list");
              memberList.innerHTML = "";
              selectedSwarmNodeUuid = null;
              leaveBtn.disabled = true;

              members.forEach(uuid => {
                const item = document.createElement("li");
                item.textContent = uuid;
                item.style.cursor = "pointer";
                item.style.padding = "4px";
                item.style.borderBottom = "1px solid #ccc";

                item.addEventListener("click", () => {
                  highlightSingle("#member-list li", item);
                  selectedSwarmNodeUuid = uuid;
                  leaveBtn.disabled = false;
                });

                memberList.appendChild(item);
              });
            })
            .catch(err => {
              console.error("Failed to fetch members:", err);
            });
        });

        list.appendChild(li);
      });
    })
    .catch(err => {
      console.error("Failed to fetch swarms:", err);
    });

  // ---- Swarm dropdown (left controls) ----
  swarmSelect.addEventListener("change", () => {
    selectedSwarmTable = swarmSelect.value || null;
    updateJoinButtonState();
  });

  // ---- Ask to Leave ----
  leaveBtn.addEventListener("click", async () => {
    if (!selectedSwarmNodeUuid) {
      leaveLog.textContent = "❌ Please select a node in the members list.";
      return;
    }

    leaveLog.textContent = `⏳ Sending leave request for ${selectedSwarmNodeUuid}...`;

    try {
      const response = await fetch("/request-leave", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nids: [selectedSwarmNodeUuid] })
      });

      const result = await response.json();
      if (result.success) {
        leaveLog.textContent = result.output || "✅ Leave request sent.";

        // After a leave, re-check if the swarm became empty; if yes, stop the heartbeat server
        try {
          if (selectedSwarmTable) {
            const check = await fetch(`/api/swarm/swarm_table/is-empty`);
            const data = await check.json();
            if (data && data.empty === true) {
              await fetch("/stop-heartbeat-server", { method: "POST" });
              leaveLog.textContent += "\n🛑 Heartbeat server stopped (swarm empty).";
            }
          }
        } catch (e) {
          console.warn("Could not verify/stop heartbeat server after leave:", e);
        }
      } else {
        leaveLog.textContent = "❌ Error: " + (result.error || "Unknown error");
      }
    } catch (err) {
      leaveLog.textContent = "❌ Request failed: " + err.message;
    }
  });
}
