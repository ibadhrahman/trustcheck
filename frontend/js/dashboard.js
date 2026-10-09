/** dashboard.js */
(async () => {
  const user = await requireAuth();
  if (!user) return;
  initSidebar('dashboard');

  // Load stats
  try {
    const stats = await api.dashboardStats();
    document.getElementById('stat-total').textContent = stats.total_orders;
    document.getElementById('stat-pending').textContent = stats.pending_orders;
    document.getElementById('stat-review').textContent = stats.needs_review_orders;
    document.getElementById('stat-confirmed').textContent = stats.confirmed_orders;
    document.getElementById('stat-suspicious').textContent = stats.suspicious_submissions;
    document.getElementById('stat-products').textContent = stats.total_products;
    document.getElementById('stat-certs').textContent = stats.total_certificates;
  } catch (e) {
    showToast('Could not load stats: ' + e.message, 'error');
  }

  // Load activity
  const activityEl = document.getElementById('activity-list');
  try {
    const events = await api.dashboardActivity();
    if (!events.length) {
      activityEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><h3>No activity yet</h3><p>Create an order or verify a payment to get started.</p></div>';
      return;
    }

    const eventIcons = {
      user_registered: '🎉', user_login: '🔑', order_created: '📋',
      order_cancelled: '❌', payment_verified: '🔍', payment_confirmed_by_seller: '✅',
      order_flagged_for_review: '⚠️', product_created: '📦', certificate_created: '🏆',
    };

    activityEl.innerHTML = events.map(ev => `
      <div style="display:flex;gap:0.75rem;align-items:flex-start;padding:0.65rem 0;border-bottom:1px solid var(--border-color);">
        <span style="font-size:1.1rem;flex-shrink:0;">${eventIcons[ev.event_type] || '📌'}</span>
        <div style="flex:1;">
          <div style="font-size:0.875rem;color:var(--text-primary);font-weight:500;">${ev.event_type.replace(/_/g, ' ')}</div>
          ${ev.detail ? `<div style="font-size:0.78rem;color:var(--text-muted);">${ev.detail}</div>` : ''}
        </div>
        <div style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap;">${formatDate(ev.created_at)}</div>
      </div>
    `).join('');
  } catch (e) {
    activityEl.innerHTML = `<div class="alert alert-error">Could not load activity: ${e.message}</div>`;
  }
})();
