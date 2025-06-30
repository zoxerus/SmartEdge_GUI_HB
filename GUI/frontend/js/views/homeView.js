// frontend/js/views/homeView.js
export function loadHomeView() {
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("[Home View] container not found");
    return;
  }

  container.innerHTML = `
    <h2>Welcome to SmartEdge</h2>
    <p>This dashboard allows you to monitor logs, database snapshots, and manage smart nodes.</p>
  `;
}
