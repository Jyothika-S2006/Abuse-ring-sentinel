/**
 * Abuse Ring Sentinel - Interactive Dashboard Application
 * Manages cluster listing, 9-feature matrix inspection, and Canvas graph visualization.
 */

let allClusters = [];
let currentClusterDetail = null;
let graphSimulation = null;

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  loadClusters();
});

function initEventListeners() {
  document.getElementById("refresh-btn").addEventListener("click", loadClusters);
  document.getElementById("search-input").addEventListener("input", filterClusters);
  document.getElementById("status-filter").addEventListener("change", filterClusters);
  document.getElementById("type-filter").addEventListener("change", filterClusters);

  // Modal controls
  document.getElementById("modal-close-btn").addEventListener("click", closeModal);
  document.getElementById("investigation-modal").addEventListener("click", (e) => {
    if (e.target.id === "investigation-modal") closeModal();
  });

  // Modal tab buttons
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPanel = document.getElementById(btn.dataset.tab);
      if (targetPanel) targetPanel.classList.add("active");
    });
  });

  // Save status button
  document.getElementById("modal-save-status-btn").addEventListener("click", updateClusterStatus);
}

async function loadClusters() {
  try {
    const res = await fetch("/api/clusters");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    allClusters = data.clusters || [];

    updateKPICards(data, allClusters);
    renderClustersTable(allClusters);
  } catch (err) {
    console.error("Failed to load clusters:", err);
    document.getElementById("clusters-tbody").innerHTML = `
      <tr>
        <td colspan="10" style="text-align: center; padding: 30px; color: #FCA5A5;">
          Failed to fetch clusters from backend API. Make sure FastAPI server is running.
        </td>
      </tr>
    `;
  }
}

function updateKPICards(data, clusters) {
  document.getElementById("kpi-total-clusters").textContent = data.total_clusters || clusters.length;
  document.getElementById("kpi-high-risk").textContent = data.high_risk_count || clusters.filter(c => c.avg_risk_score >= 0.70).length;

  const totalMembers = clusters.reduce((sum, c) => sum + (c.cluster_size || 0), 0);
  document.getElementById("kpi-linked-accounts").textContent = totalMembers;

  const totalVolume = clusters.reduce((sum, c) => sum + (c.total_volume || 0), 0);
  document.getElementById("kpi-total-volume").textContent = `$${totalVolume.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;

  document.getElementById("kpi-investigation").textContent = data.under_investigation_count || clusters.filter(c => c.status === "UNDER_INVESTIGATION").length;
}

function filterClusters() {
  const searchTerm = document.getElementById("search-input").value.toLowerCase().trim();
  const statusFilter = document.getElementById("status-filter").value;
  const typeFilter = document.getElementById("type-filter").value;

  const filtered = allClusters.filter(c => {
    const matchSearch = !searchTerm || 
      c.cluster_id.toLowerCase().includes(searchTerm) || 
      (c.primary_shared_signal && c.primary_shared_signal.toLowerCase().includes(searchTerm)) ||
      (c.detected_ring_type && c.detected_ring_type.toLowerCase().includes(searchTerm));

    const matchStatus = !statusFilter || c.status === statusFilter;
    const matchType = !typeFilter || c.detected_ring_type === typeFilter;

    return matchSearch && matchStatus && matchType;
  });

  renderClustersTable(filtered);
}

function renderClustersTable(clusters) {
  const tbody = document.getElementById("clusters-tbody");
  const countLabel = document.getElementById("cluster-count-label");
  countLabel.textContent = `${clusters.length} Cluster${clusters.length === 1 ? '' : 's'} Shown`;

  if (clusters.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" style="text-align: center; padding: 40px; color: var(--text-muted);">
          No clusters matched your filter criteria.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = clusters.map(c => {
    const risk = c.avg_risk_score;
    let badgeClass = "badge-low";
    let riskLabel = "Low Risk";
    let fillColor = "#A7F3D0";

    if (risk >= 0.70) {
      badgeClass = "badge-high";
      riskLabel = "High Risk";
      fillColor = "#FCA5A5";
    } else if (risk >= 0.30) {
      badgeClass = "badge-medium";
      riskLabel = "Medium";
      fillColor = "#FDE68A";
    }

    const typeBadge = c.detected_ring_type ? `<span class="badge badge-neutral">${c.detected_ring_type.replace('_', ' ').toUpperCase()}</span>` : '--';

    return `
      <tr>
        <td><span class="token-id">${c.cluster_id}</span></td>
        <td><strong>${c.cluster_size}</strong> accts</td>
        <td>
          <div class="mini-score-bar">
            <span class="badge ${badgeClass}">${(risk * 100).toFixed(1)}%</span>
            <div class="progress-track">
              <div class="progress-fill" style="width: ${Math.min(100, Math.max(5, risk * 100))}%; background: ${fillColor};"></div>
            </div>
          </div>
        </td>
        <td>${typeBadge}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: var(--text-secondary);">${c.primary_shared_signal || 'multi-signal'}</td>
        <td>${(c.graph_density).toFixed(2)}</td>
        <td>${(c.decline_rate * 100).toFixed(1)}%</td>
        <td>${(c.rapid_drain_ratio * 100).toFixed(1)}%</td>
        <td>
          <span style="font-size: 11px; font-weight: 600; color: ${c.status === 'CONFIRMED_FRAUD' ? '#FCA5A5' : c.status === 'DISMISSED_LEGIT' ? '#A7F3D0' : '#FDE68A'}">
            ${c.status.replace('_', ' ')}
          </span>
        </td>
        <td>
          <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 11px;" onclick="openClusterModal('${c.cluster_id}')">
            Investigate
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function openClusterModal(clusterId) {
  try {
    const res = await fetch(`/api/clusters/${clusterId}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();
    currentClusterDetail = data;

    // Header values
    document.getElementById("modal-cluster-id").textContent = data.cluster.cluster_id;
    document.getElementById("modal-status-select").value = data.cluster.status;

    const risk = data.cluster.avg_risk_score;
    const badge = document.getElementById("modal-risk-badge");
    badge.className = `badge ${risk >= 0.70 ? 'badge-high' : risk >= 0.30 ? 'badge-medium' : 'badge-low'}`;
    badge.textContent = `Risk: ${(risk * 100).toFixed(1)}% (${data.cluster.detected_ring_type || 'Unknown'})`;

    const gtTag = document.getElementById("modal-gt-tag");
    const gt = data.ground_truth_summary;
    gtTag.textContent = `Ground Truth: ${gt.dominant_ring_id} (${(gt.member_abuse_ratio * 100).toFixed(0)}% Abuse)`;

    // 9 Features Matrix
    renderFeatureMatrix(data.cluster);

    // Tab counts & sub-tables
    document.getElementById("tab-member-count").textContent = data.nodes.length;
    document.getElementById("tab-inst-count").textContent = data.instruments.length + data.payout_destinations.length;
    document.getElementById("tab-tx-count").textContent = data.transactions.length;

    renderMemberRoster(data.nodes);
    renderInstrumentsTable(data.instruments, data.payout_destinations);
    renderTransactionsTable(data.transactions);

    // Render Canvas Graph Visualization
    renderEntityGraph(data.nodes, data.edges);

    // Show modal
    document.getElementById("investigation-modal").classList.add("active");
  } catch (err) {
    console.error("Failed to open cluster detail:", err);
    alert(`Could not load details for cluster ${clusterId}: ${err.message}`);
  }
}

function closeModal() {
  document.getElementById("investigation-modal").classList.remove("active");
  if (graphSimulation) {
    cancelAnimationFrame(graphSimulation);
    graphSimulation = null;
  }
}

function renderFeatureMatrix(c) {
  const container = document.getElementById("modal-feature-matrix");
  const feats = [
    { label: "1. Cluster Size", val: `${c.cluster_size} accounts` },
    { label: "2. Graph Density", val: (c.graph_density).toFixed(3) },
    { label: "3. Shared Device", val: `${(c.shared_device_ratio * 100).toFixed(1)}%` },
    { label: "4. Shared IP", val: `${(c.shared_ip_ratio * 100).toFixed(1)}%` },
    { label: "5. Shared Payout", val: `${(c.shared_payout_ratio * 100).toFixed(1)}%` },
    { label: "6. Avg Risk Score", val: `${(c.avg_risk_score * 100).toFixed(1)}%` },
    { label: "7. Tx Velocity", val: `${(c.tx_velocity).toFixed(1)} tx/acct` },
    { label: "8. Decline Rate", val: `${(c.decline_rate * 100).toFixed(1)}%` },
    { label: "9. Rapid Drain", val: `${(c.rapid_drain_ratio * 100).toFixed(1)}%` },
  ];

  container.innerHTML = feats.map(f => `
    <div class="feature-box">
      <div class="feat-label">${f.label}</div>
      <div class="feat-val">${f.val}</div>
    </div>
  `).join("");
}

function renderMemberRoster(nodes) {
  const tbody = document.getElementById("modal-members-tbody");
  tbody.innerHTML = nodes.map(n => `
    <tr>
      <td><span class="token-id">${n.account_id}</span></td>
      <td>${n.user_name}</td>
      <td style="font-family: var(--font-mono); font-size: 11px;">${n.email}</td>
      <td style="font-family: var(--font-mono); font-size: 11px;">${n.device_id.substring(0, 18)}...</td>
      <td style="font-family: var(--font-mono); font-size: 11px;">${n.ip_address}</td>
      <td>
        <span class="badge ${n.kyc_status === 'verified' ? 'badge-low' : 'badge-high'}" style="font-size: 10px;">
          ${n.kyc_status}
        </span>
      </td>
      <td><strong>${(n.risk_score * 100).toFixed(0)}%</strong></td>
      <td><span class="badge badge-neutral">${n.account_role}</span></td>
    </tr>
  `).join("");
}

function renderInstrumentsTable(insts, payouts) {
  const instTbody = document.getElementById("modal-instruments-tbody");
  instTbody.innerHTML = insts.length ? insts.map(i => `
    <tr>
      <td><span class="token-id">${i.account_id}</span></td>
      <td>${i.instrument_type}</td>
      <td><code>${i.card_bin || '--'}</code></td>
      <td><code>${i.card_last4 || '--'}</code></td>
      <td style="font-family: var(--font-mono); font-size: 10px;">${(i.card_fingerprint || '').substring(0, 16)}...</td>
    </tr>
  `).join("") : `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No payment cards registered</td></tr>`;

  const payTbody = document.getElementById("modal-payouts-tbody");
  payTbody.innerHTML = payouts.length ? payouts.map(p => `
    <tr>
      <td><span class="token-id">${p.account_id}</span></td>
      <td>${p.destination_type}</td>
      <td>${p.holder_name}</td>
      <td style="font-family: var(--font-mono); font-size: 10px; color: var(--accent-cyan);">${(p.destination_hash || '').substring(0, 16)}...</td>
    </tr>
  `).join("") : `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No payout endpoints registered</td></tr>`;
}

function renderTransactionsTable(txs) {
  const tbody = document.getElementById("modal-tx-tbody");
  tbody.innerHTML = txs.length ? txs.map(t => {
    const isDeclined = t.status.startsWith('declined') || t.status === 'failed';
    return `
      <tr>
        <td><span class="token-id">${t.transaction_id}</span></td>
        <td><span class="token-id">${t.account_id}</span></td>
        <td style="font-size: 11px; color: var(--text-secondary);">${t.timestamp.replace('T', ' ').substring(0, 19)}</td>
        <td><strong>$${t.amount.toFixed(2)}</strong></td>
        <td><span class="badge badge-neutral">${t.transaction_type}</span></td>
        <td>
          <span class="badge ${isDeclined ? 'badge-high' : 'badge-low'}" style="font-size: 10px;">
            ${t.status}
          </span>
        </td>
        <td>${t.merchant_id} (${t.merchant_category})</td>
      </tr>
    `;
  }).join("") : `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No transactions recorded</td></tr>`;
}

async function updateClusterStatus() {
  if (!currentClusterDetail) return;
  const newStatus = document.getElementById("modal-status-select").value;
  const clusterId = currentClusterDetail.cluster.cluster_id;

  try {
    const res = await fetch(`/api/clusters/${clusterId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus })
    });
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const updated = await res.json();
    alert(`Status for ${clusterId} updated to: ${updated.status}`);
    loadClusters();
  } catch (err) {
    console.error("Failed to update status:", err);
    alert(`Error updating status: ${err.message}`);
  }
}

/**
 * Force-directed Canvas Entity Graph Renderer
 */
function renderEntityGraph(nodes, edges) {
  const canvas = document.getElementById("cluster-graph-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio || 800;
  canvas.height = rect.height * window.devicePixelRatio || 380;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

  const width = rect.width;
  const height = rect.height;

  // Initialize node physics positions
  const nodeMap = {};
  const simNodes = nodes.map((n, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI;
    const radius = Math.min(width, height) * 0.32;
    const nodeObj = {
      id: n.account_id,
      x: width / 2 + Math.cos(angle) * radius + (Math.random() - 0.5) * 20,
      y: height / 2 + Math.sin(angle) * radius + (Math.random() - 0.5) * 20,
      vx: 0,
      vy: 0,
      radius: n.is_core ? 9 : 6,
      risk: n.risk_score,
      isCore: n.is_core,
      name: n.user_name
    };
    nodeMap[n.account_id] = nodeObj;
    return nodeObj;
  });

  const simEdges = edges.map(e => ({
    source: nodeMap[e.source],
    target: nodeMap[e.target],
    signal: e.signal_type,
    weight: e.weight
  })).filter(e => e.source && e.target);

  // Signal color palette
  const signalColors = {
    "shared_device": "#38BDF8",
    "shared_ip": "#60A5FA",
    "shared_card_fingerprint": "#C084FC",
    "shared_payout_destination": "#F97316",
    "p2p_transfer": "#34D399",
  };

  let iteration = 0;
  function stepSimulation() {
    // Basic force layout step
    // 1. Repulsion between nodes
    for (let i = 0; i < simNodes.length; i++) {
      for (let j = i + 1; j < simNodes.length; j++) {
        const dx = simNodes[j].x - simNodes[i].x;
        const dy = simNodes[j].y - simNodes[i].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        if (dist < 180) {
          const force = (180 - dist) / dist * 0.08;
          simNodes[i].vx -= dx * force;
          simNodes[i].vy -= dy * force;
          simNodes[j].vx += dx * force;
          simNodes[j].vy += dy * force;
        }
      }
    }

    // 2. Attraction along edges
    for (const edge of simEdges) {
      const dx = edge.target.x - edge.source.x;
      const dy = edge.target.y - edge.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetDist = 70;
      const force = (dist - targetDist) * 0.02 * (edge.weight || 1);
      edge.source.vx += (dx / dist) * force;
      edge.source.vy += (dy / dist) * force;
      edge.target.vx -= (dx / dist) * force;
      edge.target.vy -= (dy / dist) * force;
    }

    // 3. Center gravity & integrate velocity
    for (const node of simNodes) {
      node.vx += (width / 2 - node.x) * 0.01;
      node.vy += (height / 2 - node.y) * 0.01;

      node.x += node.vx * 0.8;
      node.y += node.vy * 0.8;
      node.vx *= 0.82;
      node.vy *= 0.82;

      // Keep in canvas bounds
      node.x = Math.max(20, Math.min(width - 20, node.x));
      node.y = Math.max(20, Math.min(height - 20, node.y));
    }

    // Draw frame
    ctx.clearRect(0, 0, width, height);

    // Draw Edges
    for (const edge of simEdges) {
      ctx.beginPath();
      ctx.moveTo(edge.source.x, edge.source.y);
      ctx.lineTo(edge.target.x, edge.target.y);
      let color = "#64748B";
      for (const sig in signalColors) {
        if (edge.signal && edge.signal.includes(sig)) {
          color = signalColors[sig];
          break;
        }
      }
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.55;
      ctx.lineWidth = Math.min(3, Math.max(1, edge.weight * 1.5));
      ctx.stroke();
      ctx.globalAlpha = 1.0;
    }

    // Draw Nodes
    for (const node of simNodes) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);
      
      let nodeColor = "#A7F3D0";
      if (node.risk >= 0.70) nodeColor = "#FCA5A5";
      else if (node.risk >= 0.30) nodeColor = "#FDE68A";

      ctx.fillStyle = nodeColor;
      ctx.fill();
      ctx.lineWidth = node.isCore ? 2.5 : 1;
      ctx.strokeStyle = "#FFFFFF";
      ctx.stroke();

      // Node label
      ctx.font = "9px Inter, sans-serif";
      ctx.fillStyle = "#94A3B8";
      ctx.textAlign = "center";
      ctx.fillText(node.id.replace('ACC_', ''), node.x, node.y + node.radius + 11);
    }

    iteration++;
    if (iteration < 120) {
      graphSimulation = requestAnimationFrame(stepSimulation);
    }
  }

  if (graphSimulation) cancelAnimationFrame(graphSimulation);
  stepSimulation();
}
