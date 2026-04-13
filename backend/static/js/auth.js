// ============================================
// HomePulse - Authentication
// ============================================

const Auth = {
  token: null,
  user: null,

  init() {
    this.token = localStorage.getItem('hp_token');
    const userData = localStorage.getItem('hp_user');
    if (userData) {
      try { this.user = JSON.parse(userData); } catch { this.clear(); }
    }
  },

  isLoggedIn() {
    return !!this.token;
  },

  isAdmin() {
    return this.user?.is_admin === true;
  },

  save(token, user) {
    this.token = token;
    this.user = user;
    localStorage.setItem('hp_token', token);
    localStorage.setItem('hp_user', JSON.stringify(user));
  },

  clear() {
    this.token = null;
    this.user = null;
    localStorage.removeItem('hp_token');
    localStorage.removeItem('hp_user');
  },

  headers() {
    if (!this.token) return {};
    return { 'Authorization': `Bearer ${this.token}` };
  },

  async apiFetch(url, opts = {}) {
    const headers = { ...this.headers(), ...(opts.headers || {}) };
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const resp = await fetch(url, { ...opts, headers, signal: controller.signal });
      if (resp.status === 401) {
        this.clear();
        throw new Error('Session expired');
      }
      return resp;
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('Request timed out');
      throw e;
    } finally {
      clearTimeout(timeout);
    }
  },

  async apiJson(url, opts = {}) {
    const resp = await this.apiFetch(url, opts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  },

  async login(username, password) {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Login failed');
    }
    const data = await resp.json();
    this.save(data.token, { username: data.username, is_admin: data.is_admin });
    return data;
  },

  async setup(username, password) {
    const resp = await fetch('/api/auth/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || 'Setup failed');
    }
    const data = await resp.json();
    this.save(data.token, { username: data.username, is_admin: data.is_admin });
    return data;
  },

  logout() {
    this.clear();
  },
};

Auth.init();
