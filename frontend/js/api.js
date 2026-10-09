/**
 * api.js — Central fetch wrapper for TrustCheck API calls.
 * All requests attach the JWT Authorization header automatically.
 */

const API_BASE = '';  // Same origin — backend serves frontend

/** Read token from localStorage */
function getToken() {
  return localStorage.getItem('tc_token');
}

/** Store token */
function setToken(token) {
  localStorage.setItem('tc_token', token);
}

/** Remove token */
function clearToken() {
  localStorage.removeItem('tc_token');
  localStorage.removeItem('tc_user');
}

/**
 * Core fetch wrapper.
 * @param {string} path - API path e.g. '/api/auth/login'
 * @param {object} options - fetch options (method, body, headers, etc.)
 * @param {boolean} requiresAuth - whether to attach Authorization header
 */
async function apiFetch(path, options = {}, requiresAuth = true) {
  const headers = { 'Content-Type': 'application/json', ...options.headers };

  if (requiresAuth) {
    const token = getToken();
    if (!token) {
      redirectToLogin();
      throw new Error('Not authenticated');
    }
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(API_BASE + path, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    redirectToLogin();
    throw new Error('Session expired. Please log in again.');
  }

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = data.detail || data.message || `Request failed (${res.status})`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }

  return data;
}

/** Multipart/form upload — does NOT set Content-Type (browser does it with boundary) */
async function apiUpload(path, formData, requiresAuth = false) {
  const token = getToken();
  if (requiresAuth && !token) { redirectToLogin(); throw new Error('Not authenticated'); }

  const headers = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(API_BASE + path, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (res.status === 401 && requiresAuth) {
    clearToken();
    redirectToLogin();
    throw new Error('Session expired.');
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || data.message || `Upload failed (${res.status})`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

function redirectToLogin() {
  const cur = window.location.pathname;
  if (!cur.includes('login') && !cur.includes('register') && !cur.includes('verify') && cur !== '/') {
    window.location.href = '/login.html?redirect=' + encodeURIComponent(cur);
  }
}

// ── Convenience methods ──────────────────────────────────────

const api = {
  // Auth
  register: (body) => apiFetch('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }, false),
  login: (body) => apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }, false),
  me: () => apiFetch('/api/auth/me'),

  // Seller
  getProfile: () => apiFetch('/api/seller/profile'),
  updateProfile: (body) => apiFetch('/api/seller/profile', { method: 'PATCH', body: JSON.stringify(body) }),
  getSellerCode: () => apiFetch('/api/seller/referral-code'),

  // Products
  createProduct: (body) => apiFetch('/api/products', { method: 'POST', body: JSON.stringify(body) }),
  getProducts: () => apiFetch('/api/products'),
  getProduct: (id) => apiFetch(`/api/products/${id}`),
  uploadCertificate: (productId, formData) => apiUpload(`/api/products/${productId}/certificate`, formData),
  verifyCertificate: (formData) => apiUpload('/api/certificates/verify', formData),
  ledgerStatus: () => apiFetch('/api/ledger/status'),

  // Orders
  createOrder: (body) => apiFetch('/api/orders', { method: 'POST', body: JSON.stringify(body) }),
  getOrders: () => apiFetch('/api/orders'),
  getOrder: (id) => apiFetch(`/api/orders/${id}`),
  getOrderByCode: (code) => apiFetch(`/api/orders/referral/${code}`),
  cancelOrder: (id) => apiFetch(`/api/orders/${id}/cancel`, { method: 'POST' }),
  confirmPayment: (id) => apiFetch(`/api/orders/${id}/confirm-payment`, { method: 'POST' }),
  markReview: (id) => apiFetch(`/api/orders/${id}/mark-review`, { method: 'POST' }),

  // Payments
  analyzeScreenshot: (formData) => apiUpload('/api/payments/analyze', formData),
  crossVerify: (formData) => apiUpload('/api/payments/cross-verify', formData),
  paymentHistory: (limit = 20) => apiFetch(`/api/payments/history?limit=${limit}`),


  // Dashboard
  dashboardStats: () => apiFetch('/api/dashboard/stats'),
  dashboardActivity: () => apiFetch('/api/dashboard/activity'),
};

// ── Toast notifications ──────────────────────────────────────

function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

// ── Auth helpers (used by all pages) ────────────────────────

async function requireAuth() {
  if (!getToken()) { redirectToLogin(); return null; }
  try {
    const data = await api.me();
    localStorage.setItem('tc_user', JSON.stringify(data));
    return data;
  } catch {
    clearToken();
    redirectToLogin();
    return null;
  }
}

function getCurrentUser() {
  try { return JSON.parse(localStorage.getItem('tc_user')); } catch { return null; }
}

function logout() {
  clearToken();
  window.location.href = '/login.html';
}

// ── Utility helpers ──────────────────────────────────────────

function formatCurrency(amount) {
  if (amount == null) return '—';
  return '₹' + Number(amount).toFixed(2);
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✓ Copied!';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 2000);
    showToast('Copied to clipboard', 'ok');
  }).catch(() => showToast('Copy failed — select and copy manually', 'error'));
}

function statusBadge(status) {
  const map = {
    pending: 'badge-pending',
    needs_review: 'badge-review',
    seller_confirmed: 'badge-confirmed',
    cancelled: 'badge-cancelled',
  };
  const label = {
    pending: 'Pending',
    needs_review: 'Needs Review',
    seller_confirmed: 'Confirmed',
    cancelled: 'Cancelled',
  };
  return `<span class="badge ${map[status] || ''}">${label[status] || status}</span>`;
}

function verdictBadge(verdict) {
  if (!verdict) return '';
  const cls = `badge-${verdict}`;
  return `<span class="badge ${cls}">${verdict.charAt(0).toUpperCase() + verdict.slice(1)}</span>`;
}

/** Render sidebar active state and user info */
function initSidebar(activePage) {
  document.querySelectorAll('.nav-item[data-page]').forEach(el => {
    el.classList.toggle('active', el.dataset.page === activePage);
  });

  const user = getCurrentUser();
  if (user) {
    const name = user.profile?.business_name || user.profile?.contact_name || user.user?.email || '';
    const email = user.user?.email || '';
    const initial = (name || email).charAt(0).toUpperCase();
    const avatar = document.getElementById('sidebar-avatar');
    const nameEl = document.getElementById('sidebar-name');
    const emailEl = document.getElementById('sidebar-email');
    if (avatar) avatar.textContent = initial;
    if (nameEl) nameEl.textContent = name || email;
    if (emailEl) emailEl.textContent = email;
  }

  // Mobile sidebar toggle
  const menuBtn = document.getElementById('mobile-menu-btn');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      overlay?.classList.toggle('show');
    });
    overlay?.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('show');
    });
  }
}
