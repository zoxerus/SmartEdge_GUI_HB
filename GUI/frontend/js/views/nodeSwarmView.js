export function loadNodeSwarmView() {
  let selectedUuid = null;
  let selectedSwarmTable = null;
  let selectedSwarmNodeUuid = null;
  let allSwarms = [];

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
          <p><strong>Status:</strong> <span id="detail-status"></span></p>
          <p><strong>Swarm:</strong> <span id="detail-swarm"></span></p>
        </div>

        <div id="join-controls">
          <label for="swarm-select">Select Swarm:</label>
          <select id="swarm-select" disabled>
            <option value="">-- Choose a swarm --</option>
          </select>
          <button id="ask-join-btn" disabled class="ask-btn">Ask to Join</button>
        </div>

        <div id="node-log" class="node-log">Waiting for logs</div>
      </div>

      <!-- Right Panel -->
      <div id="swarm-panel" class="panel">
        <h2>Available Swarms</h2>
        <div class="info-box">
          <ul id="swarm-list" class="list-box"></ul>

          <div id="swarm-members">
            <h3>Swarm Members</h3>
            <ul id="member-list" class="list-unstyled"></ul>

            <!-- Leave Action Section -->
            <div id="leave-controls" style="margin-top: 10px;">
              <button id="ask-leave-btn" disabled class="ask-btn">Ask to Leave</button>
              <div id="leave-log" class="node-log" style="margin-top: 10px;">Waiting for leave logs</div>
            </div>
          </div>
        </div>
      </div>

  `;

  const swarmSelect = document.getElementById("swarm-select");
  const askButton = document.getElementById("ask-join-btn");
  const logBox = document.getElementById("node-log");

  // Helper to check if we can enable the Ask button
  function updateJoinButtonState() {
    askButton.disabled = !(selectedUuid && selectedSwarmTable);
  }

  // Fetch ART nodes
  fetch("/art-nodes")
    .then(res => res.json())
    .then(nodes => {
      const list = document.getElementById("art-node-list");
      if (!Array.isArray(nodes)) throw new Error("Invalid response format: expected array");

      nodes.forEach(node => {
        const div = document.createElement("div");
        div.textContent = node.uuid;
        div.className = "art-node-item";
        div.style.cursor = "pointer";
        div.style.padding = "4px";
        div.style.borderBottom = "1px solid #ccc";

        div.addEventListener("click", () => {
          // Highlight
          document.querySelectorAll(".art-node-item").forEach(el => el.classList.remove("selected"));
          div.classList.add("selected");

          // Set selected node
          selectedUuid = node.uuid;
          selectedSwarmTable = null;
          askButton.disabled = true;
          swarmSelect.disabled = false;

          // Update details
          document.getElementById("detail-uuid").textContent = node.uuid;
          document.getElementById("detail-status").textContent = node.status || "-";
          document.getElementById("detail-swarm").textContent = node.swarm_id || "-";

          // Populate swarm dropdown
          swarmSelect.innerHTML = `<option value="">-- Choose a swarm --</option>`;
          allSwarms.forEach(swarm => {
            const opt = document.createElement("option");
            opt.value = swarm.table;
            opt.textContent = swarm.name;
            swarmSelect.appendChild(opt);
          });
        });

        list.appendChild(div);
      });
    })
    .catch(err => {
      console.error("Failed to fetch ART nodes:", err);
    });

  // Fetch available swarms
  fetch("/swarms")
    .then(res => res.json())
    .then(swarms => {
      allSwarms = swarms;
      const list = document.getElementById("swarm-list");
      if (!Array.isArray(swarms)) throw new Error("Invalid response format for swarms");

      swarms.forEach((swarm, index) => {
        const li = document.createElement("li");
        li.textContent = swarm.name;
        li.style.cursor = "pointer";
        li.style.padding = "4px";
        li.style.borderBottom = "1px solid #ccc";

        li.addEventListener("click", () => {
          document.querySelectorAll("#swarm-list li").forEach(el => el.classList.remove("selected"));
          li.classList.add("selected");
          selectedSwarmTable = swarm.table;  
          fetch(`/swarms/${swarm.table}`)
            .then(res => res.json())
            .then(members => {
              const memberList = document.getElementById("member-list");
              memberList.innerHTML = "";
              members.forEach(uuid => {
                const item = document.createElement('li');
                item.textContent = uuid;
                item.style.cursor = "pointer";
                item.style.padding = "4px";
                item.style.borderBottom = "1px solid #ccc";
              
                item.addEventListener('click', () => {
                  document.querySelectorAll('#member-list li').forEach(el => el.classList.remove('selected'));
                  item.classList.add('selected');
                  selectedSwarmNodeUuid = uuid;
                  document.getElementById("ask-leave-btn").disabled = false;
                });
              
                memberList.appendChild(item);
              });
              
            })
            .catch(err => {
              console.error("Failed to fetch swarm members:", err);
            });
        });

        list.appendChild(li);
      });
    })
    .catch(err => {
      console.error("Failed to fetch swarms:", err);
    });

  // Handle swarm dropdown selection
  swarmSelect.addEventListener("change", () => {
    selectedSwarmTable = swarmSelect.value || null;
    updateJoinButtonState();
  });

  // Handle Ask to Join click
  askButton.addEventListener("click", async () => {
    if (!selectedUuid || !selectedSwarmTable) {
      logBox.textContent = "❌ Please select both a node and a swarm.";
      return;
    }

    logBox.textContent = `⏳ Sending join request for ${selectedUuid} to swarm "${selectedSwarmTable}"...`;

    try {
      const response = await fetch("/request-join", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          uuid: selectedUuid,
          swarm: selectedSwarmTable
        })
      });

      const result = await response.json();

      if (result.success) {
        logBox.textContent = result.output || "✅ Join request sent.";
      } else {
        logBox.textContent = "❌ Error: " + (result.error || "Unknown error");
      }
    } catch (err) {
      logBox.textContent = "❌ Request failed: " + err.message;
    }
  });

  document.getElementById("ask-leave-btn").addEventListener("click", async () => {
    const leaveLog = document.getElementById("leave-log");

    if (!selectedSwarmNodeUuid || !selectedSwarmTable) {
      leaveLog.textContent = "❌ Please select both a swarm and a node to leave.";
      return;
    }

    leaveLog.textContent = `⏳ Sending leave request for ${selectedSwarmNodeUuid} from swarm "${selectedSwarmTable}"...`;

    try {
      const response = await fetch("/request-leave", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          nids: [selectedSwarmNodeUuid]  // ✅ Use raw UUID
        })
      });

      const result = await response.json();

      if (result.success) {
        leaveLog.textContent = result.output || "✅ Leave request sent.";
      } else {
        leaveLog.textContent = "❌ Error: " + (result.error || "Unknown error");
      }
    } catch (err) {
      leaveLog.textContent = "❌ Request failed: " + err.message;
    }
  });

  
}


