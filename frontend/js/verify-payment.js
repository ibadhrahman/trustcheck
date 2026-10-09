/** verify-payment.js */
(async () => {
  const token = getToken();
  let user = null;
  if (token) {
    try {
      user = await api.me();
      localStorage.setItem('tc_user', JSON.stringify(user));
      initSidebar('verify');
    } catch {
      clearToken();
    }
  }

  // If public buyer without login, adjust layout
  if (!user) {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.style.display = 'none';
    const main = document.querySelector('.main-content');
    if (main) {
      main.style.marginLeft = '0';
      main.style.maxWidth = '860px';
      main.style.margin = '1.5rem auto';
    }
    const mobileBar = document.querySelector('.mobile-nav-bar');
    if (mobileBar) {
      mobileBar.innerHTML = `
        <div style="display:flex;align-items:center;gap:0.6rem;">
          <div class="logo-icon">TC</div>
          <div class="logo-text">TrustCheck</div>
        </div>
        <div style="margin-left:auto;"><a href="/login.html" class="btn btn-ghost btn-sm">Seller Sign In</a></div>
      `;
    }
    const histSection = document.getElementById('history-card') || document.querySelector('.card:has(#history-table)');
    if (histSection) histSection.style.display = 'none';
  } else {
    loadHistory();
  }

  // Pre-fill code from URL
  const params = new URLSearchParams(window.location.search);
  if (params.get('code')) document.getElementById('verify-code').value = params.get('code');

  // Screenshot preview
  const input = document.getElementById('screenshot-input');
  const preview = document.getElementById('img-preview');
  const previewImg = document.getElementById('preview-img');
  const zone = document.getElementById('upload-zone');

  input.addEventListener('change', () => {
    const file = input.files[0];
    if (file) {
      previewImg.src = URL.createObjectURL(file);
      preview.classList.remove('hidden');
    }
  });

  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault(); zone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) { input.files = e.dataTransfer.files; previewImg.src = URL.createObjectURL(file); preview.classList.remove('hidden'); }
  });

  // Form submit
  document.getElementById('verify-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('verify-error');
    errEl.classList.add('hidden');

    const code = document.getElementById('verify-code').value.trim();
    const txId = document.getElementById('verify-txid').value.trim();
    const file = input.files[0];

    if (!code) {
      errEl.textContent = 'Please enter the order referral code.';
      errEl.classList.remove('hidden');
      return;
    }

    const btn = document.getElementById('verify-btn');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Analysing…';

    try {
      const fd = new FormData();
      fd.append('order_referral_code', code);
      if (txId) fd.append('submitted_tx_id', txId);
      if (file) fd.append('screenshot', file);

      const result = await api.crossVerify(fd);
      renderResult(result);
      loadHistory();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Analyse & Cross-Verify';
    }
  });

  loadHistory();
})();

let _lastOrderId = null;

function renderResult(r) {
  _lastOrderId = r.order_id;
  document.getElementById('result-section').classList.remove('hidden');
  document.getElementById('result-section').scrollIntoView({ behavior: 'smooth' });

  // Verification Transaction ID setup
  const vTxId = r.verification_tx_id || r.order_referral_code || '—';
  const txEl = document.getElementById('res-verification-txid');
  if (txEl) txEl.textContent = vTxId;

  const copyBtn = document.getElementById('btn-copy-txid');
  if (copyBtn) {
    copyBtn.onclick = () => {
      navigator.clipboard.writeText(vTxId).then(() => {
        showToast('Verification Transaction ID copied: ' + vTxId, 'ok');
      });
    };
  }

  const risk = r.risk;
  const ring = document.getElementById('risk-score-ring');
  ring.textContent = risk.score;
  ring.className = `risk-score-ring ${risk.verdict}`;

  const verdictEl = document.getElementById('risk-verdict');
  verdictEl.textContent = risk.verdict.toUpperCase();
  verdictEl.className = `risk-verdict-badge text-${risk.verdict === 'genuine' ? 'ok' : risk.verdict === 'careful' ? 'warning' : 'error'}`;

  // Reasons
  const icons = { ok: '✅', warning: '⚠️', error: '🚨' };
  document.getElementById('risk-reasons').innerHTML = risk.reasons.map(r =>
    `<div class="reason-item ${r.level}"><span class="reason-icon">${icons[r.level] || '•'}</span><span>${r.text}</span></div>`
  ).join('');

  document.getElementById('risk-disclaimer').textContent = risk.disclaimer;

  // Duplicate warning
  if (r.duplicate_warning) {
    document.getElementById('dup-warning').classList.remove('hidden');
    document.getElementById('dup-detail-card').classList.remove('hidden');
    document.getElementById('dup-detail-text').textContent = r.duplicate_details || '';
  } else {
    document.getElementById('dup-warning').classList.add('hidden');
    document.getElementById('dup-detail-card').classList.add('hidden');
  }

  // Comparison table
  const ext = r.extracted_fields;
  const rows = [
    { label: 'Amount', exp: formatCurrency(r.expected_amount), got: ext?.amount != null ? formatCurrency(ext.amount) : null, match: ext?.amount != null && Math.abs(ext.amount - r.expected_amount) < 0.01 },
    { label: 'Payee Name', exp: r.expected_payee_name || '—', got: ext?.payee_name || null, match: ext?.payee_name && r.expected_payee_name && ext.payee_name.toLowerCase().includes(r.expected_payee_name.toLowerCase().substring(0,5)) },
    { label: 'UPI ID', exp: r.expected_upi_id || '—', got: ext?.payee_upi_id || null, match: null },
    { label: 'Transaction ID', exp: r.submitted_tx_id || '—', got: ext?.tx_id || null, match: ext?.tx_id && r.submitted_tx_id && ext.tx_id.toUpperCase() === r.submitted_tx_id.toUpperCase() },
    { label: 'Date', exp: '—', got: ext?.date_str || null, match: null },
    { label: 'Time', exp: '—', got: ext?.time_str || null, match: null },
    { label: 'App', exp: '—', got: ext?.app_indicator || null, match: null },
    { label: 'Status', exp: '—', got: ext?.status_text || null, match: null },
  ];

  const grid = document.querySelector('.compare-grid');
  // Clear old rows beyond headers
  while (grid.children.length > 2) grid.removeChild(grid.lastChild);

  rows.forEach(row => {
    const expCell = document.createElement('div');
    expCell.className = 'compare-cell';
    expCell.innerHTML = `<span style="font-size:0.72rem;color:var(--text-muted);display:block;">${row.label}</span>${row.exp}`;

    const gotCell = document.createElement('div');
    const gotText = row.got != null ? row.got : '<span class="unknown">Unknown</span>';
    const cls = row.got == null ? 'unknown' : row.match === true ? 'match' : row.match === false ? 'mismatch' : '';
    gotCell.className = `compare-cell ${cls}`;
    gotCell.innerHTML = `<span style="font-size:0.72px;color:transparent;display:block;">${row.label}</span>${gotText}`;

    grid.appendChild(expCell);
    grid.appendChild(gotCell);
  });

  // Confirm / flag buttons
  document.getElementById('btn-confirm-payment').onclick = async () => {
    if (!confirm('Confirm that you have verified the credit in your bank/UPI app?')) return;
    try {
      await api.confirmPayment(_lastOrderId);
      showToast('Order confirmed!', 'ok');
    } catch (e) { showToast(e.message, 'error'); }
  };

  document.getElementById('btn-flag-review').onclick = async () => {
    try {
      await api.markReview(_lastOrderId);
      showToast('Order flagged for review.', 'warning');
    } catch (e) { showToast(e.message, 'error'); }
  };
}

async function loadHistory() {
  const el = document.getElementById('history-container');
  try {
    const history = await api.paymentHistory(10);
    if (!history.length) {
      el.innerHTML = '<div class="empty-state" style="padding:1.5rem;"><p>No verifications yet.</p></div>';
      return;
    }
    el.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Order ID</th><th>Verification TX ID</th><th>Bank Ref</th><th>Amount (extracted)</th>
            <th>Verdict</th><th>Viewpoint</th><th>Date</th>
          </tr></thead>
          <tbody>
            ${history.map(h => `
              <tr>
                <td>#${h.order_id}</td>
                <td class="mono" style="color:var(--accent-color);font-weight:600;">${h.verification_tx_id || '—'}</td>
                <td class="mono">${h.submitted_tx_id || h.extracted_tx_id || '—'}</td>
                <td>${h.extracted_amount != null ? formatCurrency(h.extracted_amount) : '<span class="text-muted">Unknown</span>'}</td>
                <td>${verdictBadge(h.risk_verdict)}</td>
                <td>${h.screenshot_viewpoint || '—'}</td>
                <td>${formatDate(h.created_at)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">Could not load history: ${e.message}</div>`;
  }
}
