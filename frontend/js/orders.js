/** orders.js */
(async () => {
  const user = await requireAuth();
  if (!user) return;
  initSidebar('orders');

  // Show create panel if hash is #create
  if (window.location.hash === '#create') {
    document.getElementById('create-order-panel').style.display = 'block';
  }

  document.getElementById('btn-new-order').addEventListener('click', () => {
    document.getElementById('create-order-panel').style.display = 'block';
    document.getElementById('create-order-panel').scrollIntoView({ behavior: 'smooth' });
  });

  // Create order
  document.getElementById('create-order-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('create-order-error');
    errEl.classList.add('hidden');

    const amount = parseFloat(document.getElementById('order-amount').value);
    if (!amount || amount <= 0) {
      errEl.textContent = 'Please enter a valid expected amount.';
      errEl.classList.remove('hidden');
      return;
    }

    const btn = document.getElementById('create-order-btn');
    btn.disabled = true; btn.textContent = 'Creating…';

    try {
      const prodText = document.getElementById('order-product') ? document.getElementById('order-product').value.trim() : '';
      const payeeName = document.getElementById('order-payee') ? document.getElementById('order-payee').value.trim() : '';
      const note = document.getElementById('order-note') ? document.getElementById('order-note').value.trim() : '';

      const body = {
        quantity: Number(document.getElementById('order-qty').value) || 1,
        expected_amount: amount,
        expected_payee_name: payeeName || null,
        customer_label: prodText || null,
        private_note: note || null,
      };

      const order = await api.createOrder(body);

      // Show result
      document.getElementById('create-order-panel').style.display = 'none';
      document.getElementById('create-order-form').reset();
      const resultEl = document.getElementById('new-order-result');
      resultEl.classList.remove('hidden');
      document.getElementById('new-order-code').textContent = order.referral_code || '—';
      document.getElementById('shareable-msg').textContent = order.shareable_message || '';
      const buyerRef = order.buyer_access_code || '';
      const buyerLink = `${window.location.origin}/buyer.html#claim=${encodeURIComponent(buyerRef)}`;
      const refEl = document.getElementById('new-buyer-ref');
      if (refEl) refEl.textContent = buyerRef || '—';
      const copyRefBtn = document.getElementById('copy-buyer-ref');
      if (copyRefBtn) copyRefBtn.onclick = () => copyToClipboard(buyerRef, copyRefBtn);
      document.getElementById('new-buyer-link').textContent = buyerLink;
      document.getElementById('copy-buyer-link').onclick = () => copyToClipboard(buyerLink, document.getElementById('copy-buyer-link'));

      const codeBtn = document.getElementById('copy-order-code');
      codeBtn.onclick = () => copyToClipboard(order.referral_code, codeBtn);
      const msgBtn = document.getElementById('copy-msg');
      msgBtn.onclick = () => copyToClipboard(order.shareable_message, msgBtn);

      showToast('Order created!', 'ok');
      loadOrders();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false; btn.textContent = 'Create Order';
    }
  });

  // Search
  document.getElementById('btn-search').addEventListener('click', async () => {
    const code = document.getElementById('search-code').value.trim();
    if (!code) return loadOrders();
    try {
      const order = await api.getOrderByCode(code);
      renderOrders([order]);
    } catch (err) {
      showToast('Code not found: ' + err.message, 'error');
    }
  });

  document.getElementById('btn-reset').addEventListener('click', () => {
    document.getElementById('search-code').value = '';
    loadOrders();
  });

  // Search on Enter
  document.getElementById('search-code').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') document.getElementById('btn-search').click();
  });

  loadOrders();
  window.setInterval(() => {
    if (document.visibilityState === 'visible') loadSellerOutcomes();
  }, 15000);
})();

async function loadOrders() {
  const container = document.getElementById('orders-container');
  container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Loading orders…</span></div>';
  try {
    const orders = await api.getOrders();
    renderOrders(orders);
    loadSellerOutcomes();
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error">Could not load orders: ${err.message}</div>`;
  }
}

async function loadSellerOutcomes() {
  const container = document.getElementById('outcome-container');
  if (!container) return;
  try {
    const reports = await api.getSellerOutcomes();
    renderSellerOutcomes(reports);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error">Could not load buyer reports: ${escapeHtml(err.message)}</div>`;
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

function renderSellerOutcomes(reports) {
  const container = document.getElementById('outcome-container');
  if (!reports.length) {
    container.innerHTML = '<p class="text-muted text-sm">No buyer outcomes recorded yet.</p>';
    return;
  }
  container.innerHTML = reports.map(report => `
    <article class="card" style="margin:0 0 .85rem;border-color:${report.status === 'resolved' ? 'var(--border-color)' : '#f0c36d'};">
      <div style="display:flex;justify-content:space-between;gap:.75rem;flex-wrap:wrap;">
        <div><strong>${escapeHtml(report.item || report.customer_label || 'Order issue')}</strong>
          <div class="text-xs text-muted">${escapeHtml(report.referral_code || '')} · ${formatCurrency(report.expected_amount)} · reported ${formatDate(report.reported_at)}</div>
        </div>
        <span class="badge ${report.outcome === 'received' || report.status === 'resolved' ? 'badge-confirmed' : 'badge-review'}">${escapeHtml(report.status.replaceAll('_', ' '))}</span>
      </div>
      ${report.outcome === 'problem' ? `<p style="margin:.7rem 0 .25rem;"><strong>Reason:</strong> ${escapeHtml((report.reason || '').replaceAll('_', ' '))}</p><p style="margin:.25rem 0 .65rem;white-space:pre-wrap;">${escapeHtml(report.description || '')}</p>` : '<p class="text-sm text-muted" style="margin:.6rem 0;">Buyer confirmed the item arrived as described.</p>'}
      ${report.response_deadline ? `<p class="text-xs text-muted">Seller response due: ${formatDate(report.response_deadline)}</p>` : ''}
      ${report.events.map(event => `
        <div class="text-xs" style="border-top:1px solid var(--border-color);padding:.55rem 0;">
          <strong>${escapeHtml(event.event_type.replaceAll('_', ' '))}</strong> · ${formatDate(event.created_at)}
          ${event.resolution_type ? ` · ${escapeHtml(event.resolution_type)}` : ''}
          ${event.message ? `<div style="white-space:pre-wrap;margin-top:.2rem;">${escapeHtml(event.message)}</div>` : ''}
          ${(event.evidence_ids || []).map(id => `<button type="button" class="btn btn-ghost btn-sm" onclick="showSellerEvidence(${report.id}, ${id})">View private photo</button>`).join(' ')}
        </div>`).join('')}
      ${report.outcome === 'problem' && report.status !== 'resolved' ? `
        <form onsubmit="submitSellerResolution(event, ${report.order_id})" style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.6rem;">
          <select class="form-input" name="resolution_type" required style="max-width:180px;">
            <option value="replacement">Offer replacement</option><option value="refund">Offer refund</option><option value="other">Other resolution</option>
          </select>
          <input class="form-input" name="message" maxlength="2000" placeholder="Explain your offer" style="flex:1;min-width:180px;">
          <button class="btn btn-primary btn-sm" type="submit">${report.status === 'resolution_offered' ? 'Update offer' : 'Send offer'}</button>
        </form>` : '<p class="text-xs text-muted" style="margin-top:.6rem;">Resolved after buyer confirmation. Report history is retained.</p>'}
    </article>`).join('');
}

async function submitSellerResolution(event, orderId) {
  event.preventDefault();
  const form = event.currentTarget;
  const body = {
    resolution_type: form.elements.resolution_type.value,
    message: form.elements.message.value.trim() || null,
  };
  try {
    await api.offerOrderResolution(orderId, body);
    showToast('Resolution offer sent to the buyer.', 'ok');
    loadSellerOutcomes();
  } catch (err) { showToast(err.message, 'error'); }
}

async function showSellerEvidence(outcomeId, evidenceId) {
  try {
    const response = await fetch(`/api/seller/order-outcomes/${outcomeId}/evidence/${evidenceId}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    if (!response.ok) throw new Error('Could not load this private photo.');
    const objectUrl = URL.createObjectURL(await response.blob());
    document.getElementById('private-evidence-modal')?.remove();
    const modal = document.createElement('div');
    modal.id = 'private-evidence-modal';
    modal.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(10,15,28,.88);display:grid;place-items:center;padding:1rem;';
    modal.innerHTML = `<button type="button" aria-label="Close photo" style="position:absolute;top:1rem;right:1rem;" class="btn btn-secondary">Close</button><img alt="Private buyer evidence photo" style="max-width:95vw;max-height:90vh;object-fit:contain;border-radius:12px;">`;
    modal.querySelector('img').src = objectUrl;
    modal.querySelector('button').onclick = () => { URL.revokeObjectURL(objectUrl); modal.remove(); };
    modal.onclick = (e) => { if (e.target === modal) { URL.revokeObjectURL(objectUrl); modal.remove(); } };
    document.body.appendChild(modal);
  } catch (err) { showToast(err.message, 'error'); }
}

function renderOrders(orders) {
  const container = document.getElementById('orders-container');
  if (!orders.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>No orders yet</h3>
        <p>Create your first order to generate a referral code.</p>
      </div>`;
    return;
  }

  container.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Referral Code</th>
          <th>Customer</th>
          <th>Amount</th>
          <th>Status</th>
          <th>Risk</th>
          <th>Created</th>
          <th>Actions</th>
        </tr></thead>
        <tbody>
          ${orders.map(o => `
            <tr>
              <td><span class="mono" style="color:var(--brand-primary-hover);font-size:0.9rem;">${o.referral_code || '—'}</span></td>
              <td>${o.customer_label || '<span class="text-muted">—</span>'}</td>
              <td style="font-weight:600;color:var(--text-primary);">${formatCurrency(o.expected_amount)}</td>
              <td>${statusBadge(o.status)}</td>
              <td>${o.last_risk_verdict ? verdictBadge(o.last_risk_verdict) : '<span class="text-muted text-xs">—</span>'}</td>
              <td>${formatDate(o.created_at)}</td>
              <td>
                <div style="display:flex;gap:0.4rem;">
                  <button class="btn btn-secondary btn-sm" onclick="verifyOrder(${o.id})">🔍 Verify</button>
                  ${o.referral_code ? `<button class="btn btn-ghost btn-sm" onclick="copyCode('${o.referral_code}', this)">📋</button>` : ''}
                  ${!['awaiting_seller', 'resolution_offered', 'resolved'].includes(o.outcome_status) ? `<button class="btn btn-ghost btn-sm" onclick="rotateBuyerLink(${o.id})">New buyer reference</button>` : ''}
                  ${o.outcome_status && o.outcome_status !== 'received' ? `<span class="badge badge-review">${o.outcome_status.replaceAll('_', ' ')}</span>` : ''}
                  ${o.status === 'pending' || o.status === 'needs_review' ?
                    `<button class="btn btn-success btn-sm" onclick="confirmOrder(${o.id})">✅</button>
                     <button class="btn btn-danger btn-sm" onclick="cancelOrder(${o.id})">✕</button>` : ''}
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>`;
}

async function rotateBuyerLink(id) {
  try {
    const result = await api.rotateBuyerAccessCode(id);
    const link = `${window.location.origin}/buyer.html#claim=${encodeURIComponent(result.access_code)}`;
    await copyToClipboard(link);
    showToast(`New reference ${result.access_code} copied! Previous reference no longer works.`, 'ok');
  } catch (err) { showToast(err.message, 'error'); }
}

function verifyOrder(orderId) {
  window.location.href = `/verify-payment.html?order_id=${encodeURIComponent(orderId)}`;
}

function copyCode(code, btn) {
  copyToClipboard(code, btn);
}

async function confirmOrder(id) {
  if (!confirm('Have you confirmed the bank credit in your UPI app? This marks the order as seller-confirmed.')) return;
  try {
    await api.confirmPayment(id);
    showToast('Order marked as confirmed.', 'ok');
    loadOrders();
  } catch (e) { showToast(e.message, 'error'); }
}

async function cancelOrder(id) {
  if (!confirm('Cancel this order?')) return;
  try {
    await api.cancelOrder(id);
    showToast('Order cancelled.', 'warning');
    loadOrders();
  } catch (e) { showToast(e.message, 'error'); }
}
