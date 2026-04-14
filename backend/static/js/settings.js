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

    // Delegated click handlers for dynamically rendered buttons
    document.getElementById('settings-overlay').addEventListener('click', (e) => {
      const delInst = e.target.closest('[data-delete-instance]');
      if (delInst) { this.deleteInstance(parseInt(delInst.dataset.deleteInstance, 10)); return; }
      const delUser = e.target.closest('[data-delete-user]');
      if (delUser) { this.deleteUser(parseInt(delUser.dataset.deleteUser, 10)); return; }
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
      <div class="section-order-item" data-key="${this._escAttr(key)}">
        <span>${labels[key] || this._escHtml(key)}</span>
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
    container.innerHTML = '<div class="loading-skeleton" style="height:200px"></div>';
    try {
      const [data, instances] = await Promise.all([
        Auth.apiJson('/api/settings/services'),
        Auth.apiJson('/api/settings/instances'),
      ]);

      const groups = {
        'Proxmox': ['PROXMOX_HOST', 'PROXMOX_USER', 'PROXMOX_TOKEN_NAME', 'PROXMOX_TOKEN_VALUE', 'PROXMOX_VERIFY_SSL'],
        'Docker': ['DOCKER_URL'],
        'Radarr': ['RADARR_URL', 'RADARR_API_KEY'],
        'Sonarr': ['SONARR_URL', 'SONARR_API_KEY'],
        'Lidarr': ['LIDARR_URL', 'LIDARR_API_KEY'],
        'Jellyfin': ['JELLYFIN_URL', 'JELLYFIN_API_KEY'],
        'Plex': ['PLEX_URL', 'PLEX_TOKEN'],
        'Tautulli': ['TAUTULLI_URL', 'TAUTULLI_API_KEY'],
        'OpenClaw': ['OPENCLAW_URL', 'OPENCLAW_API_KEY', 'OPENCLAW_MODEL'],
        'Dashboard': ['REFRESH_INTERVAL'],
      };

      // Config fields for each instance type
      this._instanceFields = {
        proxmox: [
          { key: 'host', label: 'Host URL', type: 'text', placeholder: 'https://192.168.1.200:8006' },
          { key: 'user', label: 'User', type: 'text', placeholder: 'root@pam' },
          { key: 'token_name', label: 'Token Name', type: 'text', placeholder: 'dashboard' },
          { key: 'token_value', label: 'Token Value', type: 'password', placeholder: 'API token' },
          { key: 'verify_ssl', label: 'Verify SSL', type: 'text', placeholder: 'false' },
        ],
        docker: [
          { key: 'host', label: 'Docker Host', type: 'text', placeholder: 'tcp://192.168.1.200:2375' },
          { key: 'url', label: 'Access URL', type: 'text', placeholder: 'http://192.168.1.200' },
        ],
      };

      let html = '';
      for (const [group, keys] of Object.entries(groups)) {
        const serviceType = group.toLowerCase();
        const canAddInstance = serviceType === 'proxmox' || serviceType === 'docker';

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
              <input type="${type}" class="settings-input service-input" data-key="${key}" value="${this._escAttr(val)}" placeholder="From .env">
            </div>`;
        }

        // Show existing additional instances for this service type
        if (canAddInstance) {
          const typeInstances = instances.filter(i => i.service_type === serviceType);
          for (const inst of typeInstances) {
            html += this._renderInstanceCard(inst);
          }
          html += `<button class="instance-add-btn" onclick="Settings.showAddInstance('${serviceType}')">+ Add ${group} Instance</button>`;
          html += `<div id="instance-form-${serviceType}" class="instance-form hidden"></div>`;
        }

        html += '</div>';
      }
      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = `<div class="settings-error">${this._escHtml(e.message)}</div>`;
    }
  },

  _renderInstanceCard(inst) {
    const esc = (s) => this._escHtml(String(s ?? ''));
    const escAttr = (s) => this._escAttr(String(s ?? ''));
    const config = inst.config || {};
    const fields = this._instanceFields[inst.service_type] || [];

    let fieldsHtml = '';
    for (const f of fields) {
      const val = config[f.key] ?? '';
      fieldsHtml += `
        <div class="settings-form-group">
          <label>${f.label}</label>
          <input type="${f.type}" class="settings-input instance-field" data-instance-id="${inst.id}" data-config-key="${escAttr(f.key)}" value="${escAttr(val)}" placeholder="${escAttr(f.placeholder || '')}">
        </div>`;
    }

    return `
      <div class="instance-card" data-instance-id="${inst.id}">
        <div class="instance-card-header">
          <input type="text" class="settings-input instance-name-input" data-instance-id="${inst.id}" value="${escAttr(inst.instance_name)}" placeholder="Instance name">
          <div class="instance-card-actions">
            <button class="instance-action-btn" onclick="Settings.saveInstance(${inst.id})" title="Save">Save</button>
            <button class="instance-action-btn" onclick="Settings.testInstance(${inst.id})" title="Test">Test</button>
            <button class="instance-action-btn danger" data-delete-instance="${inst.id}" title="Delete">Delete</button>
          </div>
        </div>
        ${fieldsHtml}
      </div>`;
  },

  showAddInstance(serviceType) {
    const formEl = document.getElementById(`instance-form-${serviceType}`);
    if (!formEl || !formEl.classList.contains('hidden')) return;

    const fields = this._instanceFields[serviceType] || [];
    let html = `
      <div class="instance-card new-instance">
        <div class="settings-form-group">
          <label>Instance Name</label>
          <input type="text" class="settings-input" id="new-instance-name-${serviceType}" placeholder="e.g. Office Server">
        </div>`;
    for (const f of fields) {
      html += `
        <div class="settings-form-group">
          <label>${f.label}</label>
          <input type="${f.type}" class="settings-input" id="new-instance-${serviceType}-${f.key}" placeholder="${this._escAttr(f.placeholder || '')}">
        </div>`;
    }
    html += `
        <div class="instance-card-actions" style="margin-top:8px">
          <button class="instance-action-btn" onclick="Settings.createInstance('${serviceType}')">Create</button>
          <button class="instance-action-btn" onclick="document.getElementById('instance-form-${serviceType}').classList.add('hidden')">Cancel</button>
        </div>
      </div>`;

    formEl.innerHTML = html;
    formEl.classList.remove('hidden');
  },

  async createInstance(serviceType) {
    const nameEl = document.getElementById(`new-instance-name-${serviceType}`);
    const name = nameEl ? nameEl.value.trim() : '';
    if (!name) { this.showToast('Instance name is required', true); return; }

    const fields = this._instanceFields[serviceType] || [];
    const config = {};
    for (const f of fields) {
      const el = document.getElementById(`new-instance-${serviceType}-${f.key}`);
      if (el && el.value) config[f.key] = el.value;
    }

    if (!config.host) { this.showToast('Host is required', true); return; }

    try {
      await Auth.apiJson('/api/settings/instances', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service_type: serviceType, instance_name: name, config }),
      });
      this.showToast(`Instance '${name}' created. Restart to apply.`);
      this.loadServices();
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  async saveInstance(instanceId) {
    const nameInput = document.querySelector(`.instance-name-input[data-instance-id="${instanceId}"]`);
    const fieldInputs = document.querySelectorAll(`.instance-field[data-instance-id="${instanceId}"]`);

    const config = {};
    fieldInputs.forEach(input => { config[input.dataset.configKey] = input.value; });

    try {
      await Auth.apiJson(`/api/settings/instances/${instanceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance_name: nameInput ? nameInput.value.trim() : undefined, config }),
      });
      this.showToast('Instance saved. Restart to apply.');
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  async testInstance(instanceId) {
    try {
      const data = await Auth.apiJson(`/api/settings/instances/${instanceId}/test`, { method: 'POST' });
      if (data.status === 'ok') {
        this.showToast(`Connection OK (HTTP ${data.code})`);
      } else {
        this.showToast(data.message || 'Connection failed', true);
      }
    } catch (e) {
      this.showToast(e.message, true);
    }
  },

  async deleteInstance(instanceId) {
    const nameInput = document.querySelector(`.instance-name-input[data-instance-id="${instanceId}"]`);
    const name = nameInput ? nameInput.value : `Instance ${instanceId}`;
    if (!confirm(`Delete instance '${name}'? This cannot be undone.`)) return;
    try {
      await Auth.apiJson(`/api/settings/instances/${instanceId}`, { method: 'DELETE' });
      this.showToast(`Instance '${name}' deleted`);
      this.loadServices();
    } catch (e) {
      this.showToast(e.message, true);
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
    container.innerHTML = '<div class="loading-skeleton" style="height:120px"></div>';
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
              <button class="user-action-btn danger" data-delete-user="${u.id}" title="Delete user">Delete</button>
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

  async deleteUser(userId) {
    const btn = document.querySelector(`[data-delete-user="${userId}"]`);
    const row = btn ? btn.closest('tr') : null;
    const username = row ? row.cells[0].textContent : `User ${userId}`;
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
    return Utils.escapeHtml(text);
  },

  _escAttr(text) {
    return Utils.escapeAttr(text);
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
