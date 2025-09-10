// frontend/js/views/homeView.js
export function loadHomeView() {
  const container = document.getElementById("view-container");
  if (!container) {
    console.error("[Home View] container not found");
    return;
  }

  container.innerHTML = `
    <h2>Welcome to Swarm Management Dashboard</h2>
    <p>This dashboard allows you to start swarm's components, monitor logs, ART snapshots, and manage smart nodes.</p>
  `;
}
