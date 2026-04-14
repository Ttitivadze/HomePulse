// ============================================
// HomePulse - Main Application
// ============================================

const App = {
  chatOpen: false,
  chatMessages: [],
  refreshInterval: null,
  isLoading: false,
  lastUpdated: null,
  openclawOnline: false,
  MAX_CHAT_HISTORY: 50,
  _timestampTimer: null,

  init() {
    this.bindEvents();
    this.loadDashboard();
    this.startAutoRefresh();
    this.checkOpenClawStatus();
  },

  bindEvents() {
    document.getElementById('refresh-btn').addEventListener('click', () => this.loadDashboard());
    document.getElementById('chat-toggle').addEventListener('click', () => this.toggleChat());
    document.getElementById('chat-close').addEventListener('click', () => this.toggleChat());
    document.getElementById('chat-send').addEventListener('click', () => this.sendMessage());
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // Retry button delegation
    document.getElementById('dashboard').addEventListener('click', (e) => {
      const btn = e.target.closest('.retry-btn');
      if (btn) {
        const section = btn.dataset.section;
        if (section) this.retrySection(section);
      }
    });
  },

  startAutoRefresh() {
    this.refreshInterval = setInterval(() => this.loadDashboard(), 30000);
  },

  // ── Main data loading ──────────────────────────────────────────

  async loadDashboard() {
    if (this.isLoading) return;
    this.isLoading = true;
    const btn = document.getElementById('refresh-btn');
    btn.classList.add('loading');

    try {
      const data = await this.fetch('/api/dashboard');
      this.renderProxmox(data.proxmox);
      this.renderDocker(data.docker);
      this.renderArr(data.radarr, data.sonarr, data.lidarr);
      this.renderStreaming(data.streaming);
      this.updateTimestamp(data.timestamp);
    } catch (e) {
      // Fallback: load sections individually
      await Promise.allSettled([
        this.loadProxmox(),
        this.loadDocker(),
        this.loadArr(),
        this.loadStreaming(),
      ]);
      this.updateTimestamp(new Date().toISOString());
    }

    btn.classList.remove('loading');
    this.isLoading = false;
  },

  // ── Per-section retry ──────────────────────────────────────────

  async retrySection(section) {
    const loaders = {
      proxmox: () => this.loadProxmox(),
      docker: () => this.loadDocker(),
      arr: () => this.loadArr(),
      streaming: () => this.loadStreaming(),
    };
    if (loaders[section]) await loaders[section]();
  },

  async loadProxmox() {
    const container = document.getElementById('proxmox-content');
    try {
      const data = await this.fetch('/api/proxmox/status');
      this.renderProxmox(data);
    } catch (e) {
      container.innerHTML = this.errorCard('Proxmox', e.message, 'proxmox');
    }
  },

  async loadDocker() {
    const container = document.getElementById('docker-content');
    try {
      const data = await this.fetch('/api/docker/containers');
      this.renderDocker(data);
    } catch (e) {
      container.innerHTML = this.errorCard('Docker', e.message, 'docker');
    }
  },

  async loadArr() {
    const container = document.getElementById('arr-content');
    try {
      const [radarr, sonarr, lidarr] = await Promise.allSettled([
        this.fetch('/api/arr/radarr'),
        this.fetch('/api/arr/sonarr'),
        this.fetch('/api/arr/lidarr'),
      ]);
      this.renderArr(
        radarr.status === 'fulfilled' ? radarr.value : null,
        sonarr.status === 'fulfilled' ? sonarr.value : null,
        lidarr.status === 'fulfilled' ? lidarr.value : null,
      );
    } catch (e) {
      container.innerHTML = this.errorCard('Arr Suite', e.message, 'arr');
    }
  },

  async loadStreaming() {
    const container = document.getElementById('streaming-content');
    try {
      const data = await this.fetch('/api/arr/streaming');
      this.renderStreaming(data);
    } catch (e) {
      container.innerHTML = this.errorCard('Streaming', e.message, 'streaming');
    }
  },

  // ── Render functions ───────────────────────────────────────────

  renderProxmox(data) {
    const container = document.getElementById('proxmox-content');
    if (!data || data.error) {
      container.innerHTML = this.errorCard('Proxmox', data?.error || 'Unknown error', 'proxmox');
      return;
    }
    if (!data.configured) {
      container.innerHTML = this.notConfigured('Proxmox', 'Set PROXMOX_HOST and API token in .env');
      return;
    }
    const escAttr = (s) => Utils.escapeAttr(String(s ?? ''));
    const openBtn = data.url
      ? `<a href="${escAttr(data.url)}" target="_blank" rel="noopener" class="section-open-btn" title="Open Proxmox">Open &#8599;</a>`
      : '';
    container.innerHTML = openBtn + data.nodes.map(node => this.renderNode(node)).join('');
  },

  renderNode(node) {
    const esc = (s) => this.escapeHtml(String(s ?? ''));
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
            <span class="status-badge ${node.status === 'online' ? 'running' : 'stopped'}">${esc(node.status)}</span>
            ${esc(node.name)}
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
    const esc = (s) => this.escapeHtml(String(s ?? ''));
    const memPercent = item.maxmem > 0 ? Math.round((item.mem / item.maxmem) * 100) : 0;
    return `
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-name">${esc(item.name)}</div>
            <div class="card-id">${type} ${esc(item.vmid)}</div>
          </div>
          <span class="status-badge ${item.status}">${esc(item.status)}</span>
        </div>
        ${item.status === 'running' ? `
        <div class="card-stats">
          <div class="stat"><div class="stat-label">CPU</div><div class="stat-value">${item.cpu}%</div></div>
          <div class="stat"><div class="stat-label">RAM</div><div class="stat-value small">${this.formatBytes(item.mem)}</div></div>
          <div class="stat"><div class="stat-label">Uptime</div><div class="stat-value small">${this.formatUptime(item.uptime)}</div></div>
        </div>` : ''}
      </div>`;
  },

  renderDocker(data) {
    const container = document.getElementById('docker-content');
    const badge = document.getElementById('docker-badge');
    if (!data || data.error) {
      container.innerHTML = this.errorCard('Docker', data?.error || 'Unknown error', 'docker');
      badge.textContent = '0';
      return;
    }
    if (!data.configured) {
      container.innerHTML = this.notConfigured('Docker', 'Mount /var/run/docker.sock in docker-compose.yml');
      badge.textContent = '0';
      return;
    }
    const hostUrl = data.host_url || '';
    const running = data.containers.filter(c => c.status === 'running').length;
    badge.textContent = `${running}/${data.containers.length}`;
    container.innerHTML = `<div class="card-grid">${data.containers.map(c => this.renderDockerCard(c, hostUrl)).join('')}</div>`;
  },

  renderDockerCard(c, hostUrl) {
    const esc = (s) => this.escapeHtml(String(s ?? ''));
    const escAttr = (s) => Utils.escapeAttr(String(s ?? ''));
    const memPercent = c.mem_limit > 0 ? Math.round((c.mem_usage / c.mem_limit) * 100) : 0;

    // Build link from first mapped host port
    const firstHostPort = c.ports.length ? c.ports[0].split('->')[0] : null;
    const baseUrl = hostUrl || ('http://' + window.location.hostname);
    const linkUrl = firstHostPort ? `${baseUrl}:${firstHostPort}` : null;
    const linkHtml = linkUrl
      ? ` <a href="${escAttr(linkUrl)}" target="_blank" rel="noopener" class="card-link" title="Open in new tab">&#8599;</a>`
      : '';

    return `
      <div class="card">
        <div class="card-header">
          <span class="status-badge ${c.status}">${esc(c.status)}</span>
          <div class="card-name-group">
            <div class="card-name">${esc(c.display_name || c.name)}${linkHtml}</div>
            ${c.display_name && c.display_name !== c.name ? `<div class="card-id">${esc(c.name)}</div>` : ''}
          </div>
        </div>
        ${c.status === 'running' ? `
        <div class="card-stats">
          <div class="stat"><div class="stat-label">CPU</div><div class="stat-value">${c.cpu_percent}%</div></div>
          <div class="stat"><div class="stat-label">RAM</div><div class="stat-value small">${this.formatBytes(c.mem_usage)}</div></div>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:${memPercent}%"></div></div>` : ''}
      </div>`;
  },

  renderArr(radarr, sonarr, lidarr) {
    const container = document.getElementById('arr-content');
    const r = radarr && !radarr.error ? radarr : null;
    const s = sonarr && !sonarr.error ? sonarr : null;
    const l = lidarr && !lidarr.error ? lidarr : null;

    if (!r?.configured && !s?.configured && !l?.configured) {
      // Check if any had errors
      const errors = [radarr, sonarr, lidarr].filter(d => d?.error);
      if (errors.length) {
        container.innerHTML = this.errorCard('Arr Suite', errors[0].error, 'arr');
      } else {
        container.innerHTML = this.notConfigured('Arr Suite', 'Configure Radarr, Sonarr, or Lidarr API keys in .env');
      }
      return;
    }

    let html = '<div class="arr-stats">';

    if (r?.configured) {
      html += `
        <div class="arr-stat-card"><div class="arr-stat-number">${r.downloaded}</div><div class="arr-stat-label">Movies Downloaded</div></div>
        <div class="arr-stat-card"><div class="arr-stat-number">${r.requested}</div><div class="arr-stat-label">Movies Requested</div></div>
        <div class="arr-stat-card"><div class="arr-stat-number">${r.total}</div><div class="arr-stat-label">Movies Total</div></div>`;
    }
    if (s?.configured) {
      html += `
        <div class="arr-stat-card"><div class="arr-stat-number">${s.total_shows}</div><div class="arr-stat-label">TV Shows (${s.monitored_shows} monitored)</div></div>
        <div class="arr-stat-card"><div class="arr-stat-number">${s.total_episodes}</div><div class="arr-stat-label">Episodes Downloaded</div></div>
        <div class="arr-stat-card"><div class="arr-stat-number">${s.missing_episodes}</div><div class="arr-stat-label">Episodes Missing</div></div>`;
    }
    if (l?.configured) {
      html += `
        <div class="arr-stat-card"><div class="arr-stat-number">${l.total_artists}</div><div class="arr-stat-label">Artists (${l.monitored_artists} monitored)</div></div>
        <div class="arr-stat-card"><div class="arr-stat-number">${l.total_albums}</div><div class="arr-stat-label">Albums</div></div>`;
    }
    html += '</div>';

    // Download queues — only show active (incomplete) downloads
    const allQueue = [
      ...(r?.queue || []).map(q => ({ ...q, source: 'Radarr' })),
      ...(s?.queue || []).map(q => ({ ...q, source: 'Sonarr' })),
      ...(l?.queue || []).map(q => ({ ...q, source: 'Lidarr' })),
    ];
    const activeQueue = allQueue.filter(q => q.sizeleft > 0);

    if (activeQueue.length > 0) {
      const esc = (s) => this.escapeHtml(String(s ?? ''));
      const INITIAL_SHOW = 3;
      const renderItem = (q) => `
        <div class="queue-item">
          <div class="queue-item-info">
            <div class="queue-item-title">${esc(q.title)}</div>
            <div class="queue-item-meta">${esc(q.source)} ${q.eta ? '&middot; ETA: ' + esc(q.eta) : ''}</div>
          </div>
          <div class="queue-item-progress">
            <div class="queue-item-percent">${q.progress}%</div>
            <div class="progress-bar"><div class="progress-fill" style="width:${q.progress}%"></div></div>
          </div>
        </div>`;
      const visible = activeQueue.slice(0, INITIAL_SHOW);
      const hidden = activeQueue.slice(INITIAL_SHOW);

      html += `<div class="queue-section">
        <div class="queue-title">Download Queue (${activeQueue.length})</div>
        ${visible.map(renderItem).join('')}
        ${hidden.length > 0 ? `
          <div class="queue-hidden" style="display:none">
            ${hidden.map(renderItem).join('')}
          </div>
          <button class="queue-expand-btn" onclick="this.previousElementSibling.style.display='block';this.style.display='none'">
            Show More (${hidden.length})
          </button>` : ''}
      </div>`;
    }

    container.innerHTML = html;
  },

  renderStreaming(data) {
    const container = document.getElementById('streaming-content');
    const badge = document.getElementById('streaming-badge');
    if (!data || data.error) {
      container.innerHTML = this.errorCard('Streaming', data?.error || 'Unknown error', 'streaming');
      badge.textContent = '0';
      return;
    }
    if (!data.configured) {
      container.innerHTML = this.notConfigured('Streaming', 'Configure Jellyfin, Plex, or Tautulli in .env');
      badge.textContent = '0';
      return;
    }

    badge.textContent = data.stream_count;

    if (data.sessions.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">&#9654;</div>No active streams</div>';
      return;
    }

    const esc = (s) => this.escapeHtml(String(s ?? ''));
    container.innerHTML = data.sessions.map(s => `
      <div class="stream-card">
        <div class="stream-indicator ${s.state === 'paused' ? 'paused' : ''}"></div>
        <div class="stream-info">
          <div class="stream-title">${esc(s.title)}</div>
          <div class="stream-meta">${s.source ? esc(s.source) + ' &middot; ' : ''}${esc(s.quality)} &middot; ${esc(s.transcode)} &middot; ${esc(s.player)}</div>
        </div>
        <div>
          <div class="stream-user">${esc(s.user)}</div>
          <div class="progress-bar" style="width:80px;margin-top:4px">
            <div class="progress-fill" style="width:${s.progress}%"></div>
          </div>
        </div>
      </div>`).join('');
  },

  // ── Timestamp ──────────────────────────────────────────────────

  updateTimestamp(isoString) {
    this.lastUpdated = new Date(isoString);
    this.renderTimestamp();
    if (this._timestampTimer) clearInterval(this._timestampTimer);
    this._timestampTimer = setInterval(() => this.renderTimestamp(), 5000);
  },

  renderTimestamp() {
    const el = document.getElementById('last-updated');
    if (!el || !this.lastUpdated) return;
    const seconds = Math.floor((Date.now() - this.lastUpdated.getTime()) / 1000);
    if (seconds < 5) el.textContent = 'Updated just now';
    else if (seconds < 60) el.textContent = `Updated ${seconds}s ago`;
    else el.textContent = `Updated ${Math.floor(seconds / 60)}m ago`;
  },

  // ── OpenClaw Chat ──────────────────────────────────────────────

  async checkOpenClawStatus() {
    const statusEl = document.getElementById('chat-status');
    try {
      const data = await this.fetch('/api/openclaw/status');
      this.openclawOnline = data.status === 'online';
      statusEl.textContent = this.openclawOnline ? 'Online' : 'Offline';
      statusEl.className = 'chat-status ' + (this.openclawOnline ? 'online' : 'offline');
    } catch {
      this.openclawOnline = false;
      statusEl.textContent = 'Offline';
      statusEl.className = 'chat-status offline';
    }
  },

  toggleChat() {
    this.chatOpen = !this.chatOpen;
    const panel = document.getElementById('chat-panel');
    const dashboard = document.getElementById('dashboard');
    panel.classList.toggle('open', this.chatOpen);
    dashboard.classList.toggle('chat-open', this.chatOpen);

    if (this.chatOpen) {
      this.checkOpenClawStatus();
      if (this.chatMessages.length === 0) {
        this.addChatMessage('assistant', 'Hello! I\'m OpenClaw, your homelab AI assistant. Ask me anything about your infrastructure, services, or let me help you troubleshoot issues.');
      }
    }
  },

  addChatMessage(role, content) {
    this.chatMessages.push({ role, content });
    // Trim chat history to keep payload size manageable
    if (this.chatMessages.length > this.MAX_CHAT_HISTORY) {
      this.chatMessages = this.chatMessages.slice(-this.MAX_CHAT_HISTORY);
    }
    this.renderChat();
  },

  renderChat(updateLastOnly) {
    const container = document.getElementById('chat-messages');
    if (updateLastOnly && container.lastElementChild) {
      // Fast path: update only the last message's text (used during streaming)
      container.lastElementChild.textContent = this.chatMessages[this.chatMessages.length - 1].content;
    } else {
      // Full rebuild: when messages are added or removed
      container.innerHTML = this.chatMessages.map(m =>
        `<div class="chat-msg ${m.role}">${this.escapeHtml(m.content)}</div>`
      ).join('');
    }
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

    // Build message payload (trim to last N messages)
    const payload = this.chatMessages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-this.MAX_CHAT_HISTORY)
      .map(m => ({ role: m.role, content: m.content }));

    // Try streaming first, fall back to non-streaming
    try {
      const resp = await fetch('/api/openclaw/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: payload }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'OpenClaw request failed');
      }

      // Stream the response token-by-token
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';

      // Insert empty assistant message for live updates
      this.chatMessages.push({ role: 'assistant', content: '' });
      const msgIdx = this.chatMessages.length - 1;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const data = trimmed.slice(6);
          if (data === '[DONE]') continue;
          try {
            const parsed = JSON.parse(data);
            const delta = parsed.choices?.[0]?.delta?.content;
            if (delta) {
              fullText += delta;
              this.chatMessages[msgIdx].content = fullText;
              this.renderChat(true);
            }
          } catch { /* partial JSON, skip */ }
        }
      }

      // If streaming produced nothing, show a fallback
      if (!fullText) {
        this.chatMessages[msgIdx].content = 'No response received.';
        this.renderChat();
      }
    } catch (e) {
      // Streaming failed — try non-streaming endpoint
      try {
        const resp = await this.fetchRaw('/api/openclaw/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: payload }),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || 'OpenClaw request failed');
        }
        const data = await resp.json();
        this.addChatMessage('assistant', data.response);
      } catch (e2) {
        this.addChatMessage('assistant', `Error: ${e2.message}. Make sure OpenClaw is configured and running.`);
      }
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  },

  // ── Helpers ────────────────────────────────────────────────────

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
    return Utils.escapeHtml(text);
  },

  notConfigured(service, hint) {
    return `<div class="not-configured">
      <strong>${service}</strong> is not configured.<br>
      <span style="font-size:12px;margin-top:4px;display:inline-block">${hint}</span>
    </div>`;
  },

  errorCard(service, message, section) {
    return `<div class="not-configured error-card">
      Failed to connect to <strong>${this.escapeHtml(service)}</strong><br>
      <span style="font-size:12px;margin-top:4px;display:inline-block;color:var(--text-muted)">${this.escapeHtml(message)}</span>
      ${section ? `<br><button class="retry-btn" data-section="${this.escapeHtml(section)}">Retry</button>` : ''}
    </div>`;
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
