// ============================================
// HomePulse - Settings Panel
// ============================================

const Settings = {
  needsSetup: false,
  uiSettings: null,

  init() {
    this.bindEvents();
    this.loadUISettings();
    this.checkSetupStatus();
  },

  bindEvents() {
    document.getElementById('settings-btn').addEventListener('click', () => this.open());
    document.getElementById('settings-close').addEventListener('click', () => this.close());
    document.getElementById('auth-submit').addEventListener('click', () => this.handleAuth());
    document.getElementById('auth-password').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.handleAuth();
    });
    document.getElementById('settings-logout').addEventListener('click', () => this.handleLogout());
    document.getElementById('ui-save').addEventListener('click', () => this.saveUI());
    document.getElementById('ui-reset').addEventListener('click', () => this.resetUI());
    document.getElementById('services-save').addEventListener('click', () => this.saveServices());
    document.getElementById('add-user-btn').addEventListener('click', () => this.addUser());

    // Tab switching
    document.querySelectorAll('.settings-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
    });

    // Close on overlay background click
    document.getElementById('settings-overlay').addEventListener('click', (e) => {
      if (e.target.id === 'settings-overlay') this.close();
    });
  },

  async checkSetupStatus() {
    try {
      const resp = await fetch('/api/auth/status');
      const data = await resp.json();
      this.needsSetup = data.needs_setup;
      // Show setup badge on gear icon
      const btn = document.getElementById('settings-btn');
      const existing = btn.querySelector('.setup-badge');
      if (this.needsSetup && !existing) {
        const badge = document.createElement('span');
        badge.className = 'setup-badge';
        btn.appendChild(badge);
      } else if (!this.needsSetup && existing) {
        existing.remove();
      }
    } catch { /* ignore */ }
  },

  async loadUISettings() {
    try {
      const resp = await fetch('/api/settings/ui');
      this.uiSettings = await resp.json();
      this.applyUISettings(this.uiSettings);
    } catch { /* use defaults from CSS */ }
  },

  applyUISettings(s) {
    if (!s) return;
    const root = document.documentElement;
    if (s.accent_color) root.style.setProperty('--accent', s.accent_color);
    if (s.bg_primary) root.style.setProperty('--bg-primary', s.bg_primary);
    if (s.bg_secondary) root.style.setProperty('--bg-secondary', s.bg_secondary);
    if (s.bg_card) root.style.setProperty('--bg-card', s.bg_card);
    if (s.text_primary) root.style.setProperty('--text-primary', s.text_primary);
    if (s.font_family) {
      const fontStack = s.font_family === 'system-ui'
        ? 'system-ui, -apple-system, sans-serif'
        : `'${s.font_family}', -apple-system, BlinkMacSystemFont, sans-serif`;
      document.body.style.fontFamily = fontStack;
    }

    // Card density
    document.body.classList.remove('density-compact');
    if (s.card_density === 'compact') {
      document.body.classList.add('density-compact');
    }

    // Section order
    if (s.section_order && Array.isArray(s.section_order)) {
      this.applySectionOrder(s.section_order);
    }
  },

  applySectionOrder(order) {
    const dashboard = document.getElementById('dashboard');
    if (!dashboard) return;
    const sectionMap = {
      'proxmox': 'proxmox-content',
      'docker': 'docker-content',
      'arr': 'arr-content',
      'streaming': 'streaming-content',
    };
    const sections = [];
    for (const key of order) {
      const contentId = sectionMap[key];
      if (!contentId) continue;
      const contentEl = document.getElementById(contentId);
      if (contentEl) {
        const section = contentEl.closest('.section');
        if (section) sections.push(section);
      }
    }
    // Reorder in DOM
    for (const section of sections) {
      dashboard.appendChild(section);
    }
  },

  open() {
    const overlay = document.getElementById('settings-overlay');
    overlay.classList.remove('hidden');

    if (this.needsSetup) {
      this.showLogin(true);
    } else if (Auth.isLoggedIn() && Auth.isAdmin()) {
      this.showPanel();
    } else {
      this.showLogin(false);
    }
  },

  close() {
    document.getElementById('settings-overlay').classList.add('hidden');
    document.getElementById('auth-error').classList.add('hidden');
  },

  showLogin(isSetup) {
    document.getElementById('settings-login').classList.remove('hidden');
    document.getElementById('settings-panel').classList.add('hidden');
    const notice = document.getElementById('setup-notice');
    const submitBtn = document.getElementById('auth-submit');
    if (isSetup) {
      notice.classList.remove('hidden');
      submitBtn.textContent = 'Create Admin Account';
    } else {
      notice.classList.add('hidden');
      submitBtn.textContent = 'Login';
    }
  },

  showPanel() {
    document.getElementById('settings-login').classList.add('hidden');
    document.getElementById('settings-panel').classList.remove('hidden');
    document.getElementById('settings-username').textContent = Auth.user?.username || '';
    this.populateUITab();
    this.switchTab('ui');
  },

  async handleAuth() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const errEl = document.getElementById('auth-error');
    errEl.classList.add('hidden');

    if (!username || !password) {
      errEl.textContent = 'Please enter username and password';
      errEl.classList.remove('hidden');
      return;
    }

    try {
      if (this.needsSetup) {
        await Auth.setup(username, password);
        this.needsSetup = false;
        this.checkSetupStatus();
      } else {
        await Auth.login(username, password);
      }
      // Clear form
      document.getElementById('auth-username').value = '';
      document.getElementById('auth-password').value = '';

      if (Auth.isAdmin()) {
        this.showPanel();
      } else {
        errEl.textContent = 'Admin access required for settings';
        errEl.classList.remove('hidden');
        Auth.logout();
      }
    } catch (e) {
      errEl.textContent = e.message;
      errEl.classList.remove('hidden');
    }
  },

  handleLogout() {
    Auth.logout();
    this.close();
  },

  switchTab(tabName) {
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.settings-tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector(`.settings-tab[data-tab="${tabName}"]`)?.classList.add('active');
    document.getElementById(`tab-${tabName}`)?.classList.add('active');

    if (tabName === 'services') this.loadServices();
    if (tabName === 'users') this.loadUsers();
  },

  // ── UI Tab ──────────────────────────────────────────────────

  populateUITab() {
    const s = this.uiSettings || {};
    document.getElementById('ui-accent-color').value = s.accent_color || '#6366f1';
    document.getElementById('ui-bg-primary').value = s.bg_primary || '#0f1117';
    document.getElementById('ui-bg-secondary').value = s.bg_secondary || '#1a1d27';
    document.getElementById('ui-bg-card').value = s.bg_card || '#1e2130';
    document.getElementById('ui-text-primary').value = s.text_primary || '#e4e6f0';
    document.getElementById('ui-font-family').value = s.font_family || 'Inter';

    const density = s.card_density || 'comfortable';
    document.querySelectorAll('input[name="density"]').forEach(r => {
      r.checked = r.value === density;
    });

    this.populateSectionOrder(s.section_order || ['proxmox', 'docker', 'arr', 'streaming']);
  },

  populateSectionOrder(order) {
    const container = document.getElementById('section-order-list');
    const labels = { proxmox: 'Proxmox VE', docker: 'Docker Containers', arr: 'Media Library', streaming: 'Active Streams' };
    container.innerHTML = order.map((key, i) => `
      <div class="section-order-item" data-key="${key}">
        <span>${labels[key] || key}</span>
        <div class="section-order-btns">
          <button class="section-order-btn" onclick="Settings.moveSectionOrder(${i}, -1)" ${i === 0 ? 'disabled' : ''}>&#9650;</button>
          <button class="section-order-btn" onclick="Settings.moveSectionOrder(${i}, 1)" ${i === order.length - 1 ? 'disabled' : ''}>&#9660;</button>
        </div>
      </div>
    `).join('');
  },

  moveSectionOrder(index, direction) {
    const items = document.querySelectorAll('.section-order-item');
    const order = Array.from(items).map(el => el.dataset.key);
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= order.length) return;
    [order[index], order[newIndex]] = [order[newIndex], order[index]];
    this.populateSectionOrder(order);
  },

  _getSectionOrder() {
    const items = document.querySelectorAll('.section-order-item');
    return Array.from(items).map(el => el.dataset.key);
  },

  async saveUI() {
    const payload = {
      accent_color: document.getElementById('ui-accent-color').value,
      bg_primary: document.getElementById('ui-bg-primary').value,
      bg_secondary: document.getElementById('ui-bg-secondary').value,
      bg_card: document.getElementById('ui-bg-card').value,
      text_primary: document.getElementById('ui-text-primary').value,
      font_family: document.getElementById('ui-font-family').value,
      card_density: document.querySelector('input[name="density"]:checked')?.value || 'comfortable',
      section_order: this._getSectionOrder(),
    };

    try {
      const data = await Auth.apiJson('/api/settings/ui', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      this.uiSettings = data;
      this.applyUISettings(data);
      this.showToast('Appearance saved');
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  async resetUI() {
    try {
      const data = await Auth.apiJson('/api/settings/ui/reset', { method: 'POST' });
      this.uiSettings = data;
      this.applyUISettings(data);
      this.populateUITab();
      this.showToast('Reset to defaults');
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  // ── Services Tab ────────────────────────────────────────────

  async loadServices() {
    const container = document.getElementById('services-form');
    try {
      const data = await Auth.apiJson('/api/settings/services');
      const groups = {
        'Proxmox': ['PROXMOX_HOST', 'PROXMOX_USER', 'PROXMOX_TOKEN_NAME', 'PROXMOX_TOKEN_VALUE', 'PROXMOX_VERIFY_SSL'],
        'Radarr': ['RADARR_URL', 'RADARR_API_KEY'],
        'Sonarr': ['SONARR_URL', 'SONARR_API_KEY'],
        'Lidarr': ['LIDARR_URL', 'LIDARR_API_KEY'],
        'Jellyfin': ['JELLYFIN_URL', 'JELLYFIN_API_KEY'],
        'Plex': ['PLEX_URL', 'PLEX_TOKEN'],
        'Tautulli': ['TAUTULLI_URL', 'TAUTULLI_API_KEY'],
        'OpenClaw': ['OPENCLAW_URL', 'OPENCLAW_API_KEY', 'OPENCLAW_MODEL'],
        'Dashboard': ['REFRESH_INTERVAL'],
      };

      let html = '';
      for (const [group, keys] of Object.entries(groups)) {
        html += `<div class="settings-section"><h3>${group}</h3>`;
        for (const key of keys) {
          const info = data[key] || {};
          const val = info.value || '';
          const type = info.is_secret ? 'password' : 'text';
          const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c);
          const overrideTag = info.has_override ? '<span class="override-badge">override</span>' : '';
          html += `
            <div class="settings-form-group">
              <label>${label} ${overrideTag}</label>
              <input type="${type}" class="settings-input service-input" data-key="${key}" value="${this._escHtml(val)}" placeholder="From .env">
            </div>`;
        }
        html += '</div>';
      }
      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="settings-error">${this._escHtml(e.message)}</div>`;
    }
  },

  async saveServices() {
    const inputs = document.querySelectorAll('.service-input');
    const configs = {};
    inputs.forEach(input => {
      configs[input.dataset.key] = input.value;
    });

    try {
      await Auth.apiJson('/api/settings/services', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ configs }),
      });
      this.showToast('Services saved. Restart to apply changes.');
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  // ── Users Tab ───────────────────────────────────────────────

  async loadUsers() {
    const container = document.getElementById('users-list');
    try {
      const users = await Auth.apiJson('/api/settings/users');
      if (users.length === 0) {
        container.innerHTML = '<div class="settings-error">No users found</div>';
        return;
      }
      let html = '<table class="users-table"><thead><tr><th>Username</th><th>Role</th><th>Created</th><th>Actions</th></tr></thead><tbody>';
      for (const u of users) {
        const isSelf = u.username === Auth.user?.username;
        html += `<tr>
          <td>${this._escHtml(u.username)}</td>
          <td><span class="role-badge ${u.is_admin ? 'admin' : ''}">${u.is_admin ? 'Admin' : 'User'}</span></td>
          <td>${u.created_at ? new Date(u.created_at).toLocaleDateString() : ''}</td>
          <td class="user-actions">
            ${!isSelf ? `
              <button class="user-action-btn" onclick="Settings.toggleAdmin(${u.id})" title="${u.is_admin ? 'Remove admin' : 'Make admin'}">${u.is_admin ? 'Demote' : 'Promote'}</button>
              <button class="user-action-btn danger" onclick="Settings.deleteUser(${u.id}, '${this._escHtml(u.username)}')" title="Delete user">Delete</button>
            ` : '<span class="text-muted">You</span>'}
          </td>
        </tr>`;
      }
      html += '</tbody></table>';
      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="settings-error">${this._escHtml(e.message)}</div>`;
    }
  },

  async addUser() {
    const username = document.getElementById('new-username').value.trim();
    const password = document.getElementById('new-password').value;
    const isAdmin = document.getElementById('new-is-admin').checked;

    if (!username || !password) {
      this.showToast('Username and password required', true);
      return;
    }

    try {
      await Auth.apiJson('/api/settings/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, is_admin: isAdmin }),
      });
      document.getElementById('new-username').value = '';
      document.getElementById('new-password').value = '';
      document.getElementById('new-is-admin').checked = false;
      this.showToast(`User '${username}' created`);
      this.loadUsers();
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  async toggleAdmin(userId) {
    try {
      await Auth.apiJson(`/api/settings/users/${userId}/admin`, { method: 'PUT' });
      this.loadUsers();
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  async deleteUser(userId, username) {
    if (!confirm(`Delete user '${username}'? This cannot be undone.`)) return;
    try {
      await Auth.apiJson(`/api/settings/users/${userId}`, { method: 'DELETE' });
      this.showToast(`User '${username}' deleted`);
      this.loadUsers();
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  // ── Helpers ─────────────────────────────────────────────────

  _escHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text ?? '');
    return div.innerHTML;
  },

  showToast(message, isError = false) {
    // Remove existing toast
    const old = document.querySelector('.settings-toast');
    if (old) old.remove();

    const toast = document.createElement('div');
    toast.className = `settings-toast ${isError ? 'error' : 'success'}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  },
};

document.addEventListener('DOMContentLoaded', () => Settings.init());
