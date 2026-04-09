// ============================================
// HomeLab Dashboard - Main Application
// ============================================

const App = {
  chatOpen: false,
  chatMessages: [],
  refreshInterval: null,
  isLoading: false,

  init() {
    this.bindEvents();
    this.loadAll();
    this.startAutoRefresh();
  },

  bindEvents() {
    document.getElementById('refresh-btn').addEventListener('click', () => this.loadAll());
    document.getElementById('chat-toggle').addEventListener('click', () => this.toggleChat());
    document.getElementById('chat-close').addEventListener('click', () => this.toggleChat());
    document.getElementById('chat-send').addEventListener('click', () => this.sendMessage());
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });
  },

  startAutoRefresh() {
    this.refreshInterval = setInterval(() => this.loadAll(), 30000);
  },

  async loadAll() {
    if (this.isLoading) return;
    this.isLoading = true;
    const btn = document.getElementById('refresh-btn');
    btn.classList.add('loading');

    await Promise.allSettled([
      this.loadProxmox(),
      this.loadDocker(),
      this.loadArr(),
      this.loadStreaming(),
    ]);

    btn.classList.remove('loading');
    this.isLoading = false;
  },

  // ---- Proxmox ----
  async loadProxmox() {
    const container = document.getElementById('proxmox-content');
    try {
      const data = await this.fetch('/api/proxmox/status');
      if (!data.configured) {
        container.innerHTML = this.notConfigured('Proxmox', 'Set PROXMOX_HOST and API token in .env');
        return;
      }
      container.innerHTML = data.nodes.map(node => this.renderNode(node)).join('');
    } catch (e) {
      container.innerHTML = this.errorCard('Proxmox', e.message);
    }
  },

  renderNode(node) {
    const memPercent = node.mem_total > 0 ? Math.round((node.mem_used / node.mem_total) * 100) : 0;
    const vms = node.vms.map(vm => this.renderVmCard(vm, 'VM')).join('');
    const cts = node.containers.map(ct => this.renderVmCard(ct, 'LXC')).join('');
    const totalGuests = node.vms.length + node.containers.length;
    const runningGuests = node.vms.filter(v => v.status === 'running').length +
                          node.containers.filter(c => c.status === 'running').length;

    return `
      <div class="node-card">
        <div class="node-header">
          <div class="node-name">
            <span class="status-badge ${node.status === 'online' ? 'running' : 'stopped'}">${node.status}</span>
            ${node.name}
          </div>
          <div class="node-stats">
            <div><span class="node-stat-label">Guests</span><br><span class="node-stat-value">${runningGuests}/${totalGuests}</span></div>
            <div><span class="node-stat-label">Uptime</span><br><span class="node-stat-value">${this.formatUptime(node.uptime)}</span></div>
          </div>
        </div>
        <div class="node-resources">
          <div class="resource-bar-container">
            <div class="resource-bar-label"><span>CPU</span><span>${node.cpu}%</span></div>
            <div class="resource-bar"><div class="resource-bar-fill cpu" style="width:${node.cpu}%"></div></div>
          </div>
          <div class="resource-bar-container">
            <div class="resource-bar-label"><span>Memory</span><span>${memPercent}% (${this.formatBytes(node.mem_used)}/${this.formatBytes(node.mem_total)})</span></div>
            <div class="resource-bar"><div class="resource-bar-fill mem" style="width:${memPercent}%"></div></div>
          </div>
        </div>
        ${node.vms.length ? `<div class="node-vms-title">Virtual Machines (${node.vms.length})</div><div class="card-grid">${vms}</div>` : ''}
        ${node.containers.length ? `<div class="node-vms-title" style="margin-top:12px">LXC Containers (${node.containers.length})</div><div class="card-grid">${cts}</div>` : ''}
      </div>`;
  },

  renderVmCard(item, type) {
    const memPercent = item.maxmem > 0 ? Math.round((item.mem / item.maxmem) * 100) : 0;
    return `
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-name">${item.name}</div>
            <div class="card-id">${type} ${item.vmid}</div>
          </div>
          <span class="status-badge ${item.status}">${item.status}</span>
        </div>
        ${item.status === 'running' ? `
        <div class="card-stats">
          <div class="stat"><div class="stat-label">CPU</div><div class="stat-value">${item.cpu}%</div></div>
          <div class="stat"><div class="stat-label">RAM</div><div class="stat-value small">${this.formatBytes(item.mem)}</div></div>
          <div class="stat"><div class="stat-label">Uptime</div><div class="stat-value small">${this.formatUptime(item.uptime)}</div></div>
        </div>` : ''}
      </div>`;
  },

  // ---- Docker ----
  async loadDocker() {
    const container = document.getElementById('docker-content');
    const badge = document.getElementById('docker-badge');
    try {
      const data = await this.fetch('/api/docker/containers');
      if (!data.configured) {
        container.innerHTML = this.notConfigured('Docker', 'Mount /var/run/docker.sock in docker-compose.yml');
        badge.textContent = '0';
        return;
      }
      const running = data.containers.filter(c => c.status === 'running').length;
      badge.textContent = `${running}/${data.containers.length}`;
      container.innerHTML = `<div class="card-grid">${data.containers.map(c => this.renderDockerCard(c)).join('')}</div>`;
    } catch (e) {
      container.innerHTML = this.errorCard('Docker', e.message);
    }
  },

  renderDockerCard(c) {
    const memPercent = c.mem_limit > 0 ? Math.round((c.mem_usage / c.mem_limit) * 100) : 0;
    const ports = c.ports.length ? `<div class="card-id" style="margin-top:4px">${c.ports.join(', ')}</div>` : '';
    return `
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-name">${c.name}</div>
            <div class="card-id">${c.image}</div>
            ${ports}
          </div>
          <span class="status-badge ${c.status}">${c.status}</span>
        </div>
        ${c.status === 'running' ? `
        <div class="card-stats">
          <div class="stat"><div class="stat-label">CPU</div><div class="stat-value">${c.cpu_percent}%</div></div>
          <div class="stat"><div class="stat-label">RAM</div><div class="stat-value small">${this.formatBytes(c.mem_usage)}</div></div>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${memPercent}%"></div></div>` : ''}
      </div>`;
  },

  // ---- Arr Suite ----
  async loadArr() {
    const container = document.getElementById('arr-content');
    try {
      const [radarr, sonarr, lidarr] = await Promise.allSettled([
        this.fetch('/api/arr/radarr'),
        this.fetch('/api/arr/sonarr'),
        this.fetch('/api/arr/lidarr'),
      ]);

      const r = radarr.status === 'fulfilled' ? radarr.value : null;
      const s = sonarr.status === 'fulfilled' ? sonarr.value : null;
      const l = lidarr.status === 'fulfilled' ? lidarr.value : null;

      if (!r?.configured && !s?.configured && !l?.configured) {
        container.innerHTML = this.notConfigured('Arr Suite', 'Configure Radarr, Sonarr, or Lidarr API keys in .env');
        return;
      }

      let html = '<div class="arr-stats">';

      if (r?.configured) {
        html += `
          <div class="arr-stat-card"><div class="arr-stat-number">${r.downloaded}</div><div class="arr-stat-label">Movies Downloaded</div></div>
          <div class="arr-stat-card"><div class="arr-stat-number">${r.missing}</div><div class="arr-stat-label">Movies Missing</div></div>`;
      }
      if (s?.configured) {
        html += `
          <div class="arr-stat-card"><div class="arr-stat-number">${s.total_shows}</div><div class="arr-stat-label">TV Shows</div></div>
          <div class="arr-stat-card"><div class="arr-stat-number">${s.total_episodes}</div><div class="arr-stat-label">Episodes Downloaded</div></div>
          <div class="arr-stat-card"><div class="arr-stat-number">${s.missing_episodes}</div><div class="arr-stat-label">Episodes Missing</div></div>`;
      }
      if (l?.configured) {
        html += `
          <div class="arr-stat-card"><div class="arr-stat-number">${l.total_artists}</div><div class="arr-stat-label">Artists</div></div>
          <div class="arr-stat-card"><div class="arr-stat-number">${l.total_albums}</div><div class="arr-stat-label">Albums</div></div>`;
      }
      html += '</div>';

      // Download queues
      const allQueue = [
        ...(r?.queue || []).map(q => ({ ...q, source: 'Radarr' })),
        ...(s?.queue || []).map(q => ({ ...q, source: 'Sonarr' })),
        ...(l?.queue || []).map(q => ({ ...q, source: 'Lidarr' })),
      ];

      if (allQueue.length > 0) {
        html += `<div class="queue-section">
          <div class="queue-title">Download Queue (${allQueue.length})</div>
          ${allQueue.map(q => `
            <div class="queue-item">
              <div class="queue-item-info">
                <div class="queue-item-title">${q.title}</div>
                <div class="queue-item-meta">${q.source} ${q.eta ? '&middot; ETA: ' + q.eta : ''}</div>
              </div>
              <div class="queue-item-progress">
                <div class="queue-item-percent">${q.progress}%</div>
                <div class="progress-bar"><div class="progress-fill" style="width:${q.progress}%"></div></div>
              </div>
            </div>`).join('')}
        </div>`;
      }

      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = this.errorCard('Arr Suite', e.message);
    }
  },

  // ---- Streaming ----
  async loadStreaming() {
    const container = document.getElementById('streaming-content');
    const badge = document.getElementById('streaming-badge');
    try {
      const data = await this.fetch('/api/arr/streaming');
      if (!data.configured) {
        container.innerHTML = this.notConfigured('Streaming', 'Configure Tautulli API key in .env');
        badge.textContent = '0';
        return;
      }

      badge.textContent = data.stream_count;

      if (data.sessions.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#9654;</div>No active streams</div>';
        return;
      }

      container.innerHTML = data.sessions.map(s => `
        <div class="stream-card">
          <div class="stream-indicator"></div>
          <div class="stream-info">
            <div class="stream-title">${s.title}</div>
            <div class="stream-meta">${s.quality} &middot; ${s.transcode} &middot; ${s.player}</div>
          </div>
          <div>
            <div class="stream-user">${s.user}</div>
            <div class="progress-bar" style="width:80px;margin-top:4px">
              <div class="progress-fill" style="width:${s.progress}%"></div>
            </div>
          </div>
        </div>`).join('');
    } catch (e) {
      container.innerHTML = this.errorCard('Streaming', e.message);
    }
  },

  // ---- OpenClaw Chat ----
  toggleChat() {
    this.chatOpen = !this.chatOpen;
    const panel = document.getElementById('chat-panel');
    const dashboard = document.getElementById('dashboard');
    panel.classList.toggle('open', this.chatOpen);
    dashboard.classList.toggle('chat-open', this.chatOpen);

    if (this.chatOpen && this.chatMessages.length === 0) {
      this.addChatMessage('assistant', 'Hello! I\'m OpenClaw, your homelab AI assistant. Ask me anything about your infrastructure, services, or let me help you troubleshoot issues.');
    }
  },

  addChatMessage(role, content) {
    this.chatMessages.push({ role, content });
    this.renderChat();
  },

  renderChat() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = this.chatMessages.map(m =>
      `<div class="chat-msg ${m.role}">${this.escapeHtml(m.content)}</div>`
    ).join('');
    container.scrollTop = container.scrollHeight;
  },

  async sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    this.addChatMessage('user', message);

    const sendBtn = document.getElementById('chat-send');
    sendBtn.disabled = true;

    // Add typing indicator
    const typingDiv = document.createElement('div');
    typingDiv.className = 'chat-msg assistant typing';
    typingDiv.textContent = 'Thinking';
    document.getElementById('chat-messages').appendChild(typingDiv);

    try {
      const resp = await this.fetchRaw('/api/openclaw/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: this.chatMessages.filter(m => m.role !== 'typing').map(m => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      typingDiv.remove();

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'OpenClaw request failed');
      }

      const data = await resp.json();
      this.addChatMessage('assistant', data.response);
    } catch (e) {
      typingDiv.remove();
      this.addChatMessage('assistant', `Error: ${e.message}. Make sure OpenClaw is configured and running.`);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  },

  // ---- Helpers ----
  async fetch(url) {
    const resp = await fetch(url);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  },

  async fetchRaw(url, opts) {
    return fetch(url, opts);
  },

  formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  formatUptime(seconds) {
    if (!seconds) return '0s';
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  },

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  notConfigured(service, hint) {
    return `<div class="not-configured">
      <strong>${service}</strong> is not configured.<br>
      <span style="font-size:12px;margin-top:4px;display:inline-block">${hint}</span>
    </div>`;
  },

  errorCard(service, message) {
    return `<div class="not-configured" style="border-color:var(--red-dim);color:var(--red)">
      Failed to connect to <strong>${service}</strong><br>
      <span style="font-size:12px;margin-top:4px;display:inline-block;color:var(--text-muted)">${message}</span>
    </div>`;
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
