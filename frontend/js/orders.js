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

  // Load products for dropdown
  try {
    const products = await api.getProducts();
    const sel = document.getElementById('order-product');
    products.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} — ₹${p.price.toFixed(2)}`;
      sel.appendChild(opt);
    });
    // Auto-fill amount on product select
    sel.addEventListener('change', () => {
      const selected = products.find(p => p.id === Number(sel.value));
      if (selected) document.getElementById('order-amount').value = selected.price;
    });
  } catch {}

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
      const body = {
        product_id: Number(document.getElementById('order-product').value) || null,
        quantity: Number(document.getElementById('order-qty').value) || 1,
        expected_amount: amount,
        expected_upi_id: document.getElementById('order-upi').value.trim() || null,
        expected_payee_name: document.getElementById('order-payee').value.trim() || null,
        customer_label: document.getElementById('order-customer').value.trim() || null,
        private_note: document.getElementById('order-note').value.trim() || null,
      };

      const order = await api.createOrder(body);

      // Show result
      document.getElementById('create-order-panel').style.display = 'none';
      document.getElementById('create-order-form').reset();
      const resultEl = document.getElementById('new-order-result');
      resultEl.classList.remove('hidden');
      document.getElementById('new-order-code').textContent = order.referral_code || '—';
      document.getElementById('shareable-msg').textContent = order.shareable_message || '';

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
})();

async function loadOrders() {
  const container = document.getElementById('orders-container');
  container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Loading orders…</span></div>';
  try {
    const orders = await api.getOrders();
    renderOrders(orders);
  } catch (err) {
    container.innerHTML = `<div class="alert alert-error">Could not load orders: ${err.message}</div>`;
  }
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
                  <button class="btn btn-secondary btn-sm" onclick="verifyOrder('${o.referral_code}')">🔍 Verify</button>
                  ${o.referral_code ? `<button class="btn btn-ghost btn-sm" onclick="copyCode('${o.referral_code}', this)">📋</button>` : ''}
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

function verifyOrder(code) {
  window.location.href = `/verify-payment.html?code=${encodeURIComponent(code)}`;
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
