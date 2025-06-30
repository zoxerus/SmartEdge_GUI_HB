export function loadNodeSwarmView() {
    const container = document.getElementById("view-container");
  
    container.innerHTML = `
        <div id="node-swarm-view" class="node-swarm-layout">
            <!-- Left Panel -->
            <div id="art-panel" class="panel">
            <h2>ART Nodes</h2>
            <div class="info-box">
            <div id="art-node-list" class="list-box"></div>
                <h3>Node Details</h3>
                <p><strong>UUID:</strong> <span id="detail-uuid"></span></p>
                <p><strong>Status:</strong> <span id="detail-status"></span></p>
                <p><strong>Swarm:</strong> <span id="detail-swarm"></span></p>
            </div>
            <button id="ask-join-btn" disabled class="ask-btn">Ask to Join</button>
            <div id="join-controls">
                <select id="swarm-select"></select>
                <button id="confirm-join-btn">Confirm</button>
            </div>
            <div id="node-log" class="node-log"></div>
            </div>

            <!-- Right Panel -->
            <div id="swarm-panel" class="panel">
            <h2>Available Swarms</h2>
            <div class="info-box">
            <ul id="swarm-list" class="list-box"></ul>
            <div id="swarm-members">
                <h3>Swarm Members</h3>
                <ul id="member-list" class="list-unstyled"></ul>
            </div>
            </div>
        </div>
        `;

  
    // ✅ Fetch ART nodes and populate left panel
    fetch('/art-nodes')
      .then(res => res.json())
      .then(nodes => {
        const list = document.getElementById('art-node-list');
        if (!Array.isArray(nodes)) throw new Error("Invalid response format: expected array");
  
        nodes.forEach(node => {
          const div = document.createElement('div');
          div.textContent = node.uuid;
          div.className = 'art-node-item';
          div.style.cursor = 'pointer';
          div.style.padding = '4px';
          div.style.borderBottom = '1px solid #ccc';
  
          div.addEventListener('click', () => {
            // Highlight selection
            document.querySelectorAll('.art-node-item').forEach(el => el.classList.remove('selected'));
            div.classList.add('selected');
          
            // Populate node details
            document.getElementById('detail-uuid').textContent = node.uuid;
            document.getElementById('detail-status').textContent = node.status || '-';
            document.getElementById('detail-swarm').textContent = node.swarm_id || '-';
            document.getElementById('node-details').style.display = 'block';
            document.getElementById('ask-join-btn').disabled = false;
          });
          
  
          list.appendChild(div);
        });
      })
      .catch(err => {
        console.error("Failed to fetch ART nodes:", err);
      });
  
    // ✅ Fetch swarm tables and populate right panel
    fetch('/swarms')
      .then(res => res.json())
      .then(swarms => {
        const list = document.getElementById('swarm-list');
        if (!Array.isArray(swarms)) throw new Error("Invalid response format for swarms");
  
        swarms.forEach((swarm, index) => {
          const li = document.createElement('li');
          li.textContent = swarm.name;
          li.style.cursor = 'pointer';
          li.style.padding = '4px';
          li.style.borderBottom = '1px solid #ccc';
  
          li.addEventListener('click', () => {
            // Highlight selection
            document.querySelectorAll('#swarm-list li').forEach(el => el.classList.remove('selected'));
            li.classList.add('selected');
          
            // Fetch and show swarm members
            fetch(`/swarms/${swarm.table}`)
              .then(res => res.json())
              .then(members => {
                const memberList = document.getElementById('member-list');
                memberList.innerHTML = '';
                members.forEach(uuid => {
                  const item = document.createElement('li');
                  item.textContent = uuid;
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
  }
  