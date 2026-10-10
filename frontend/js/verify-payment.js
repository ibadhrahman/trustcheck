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
        <a href="/" style="display:flex;align-items:center;gap:0.6rem;text-decoration:none;color:inherit;" aria-label="TrustCheck home">
          <img src="/logo.png" alt="TrustCheck" style="width:28px;height:28px;object-fit:contain;border-radius:6px;">
          <div class="logo-text">TrustCheck</div>
        </a>
        <div style="margin-left:auto;"><a href="/login.html" class="btn btn-ghost btn-sm">Seller Sign In</a></div>
      `;
    }
  } else {
    loadHistory();
  }

  // Handle Order ID / Code from URL
  const params = new URLSearchParams(window.location.search);
  const orderParam = (params.get('order_id') || params.get('id') || params.get('code') || '').trim();
  const orderIdInput = document.getElementById('verify-order-id');
  const activeOrderBadge = document.getElementById('active-order-badge');
  const activeCodeDisplay = document.getElementById('active-code-display');

  if (orderParam) {
    if (orderIdInput) orderIdInput.value = orderParam;
    if (activeCodeDisplay) activeCodeDisplay.textContent = orderParam.startsWith('#') ? orderParam : `#${orderParam}`;
    if (activeOrderBadge) activeOrderBadge.classList.remove('hidden');
  }

  // Screenshot upload preview & drag-drop
  const fileInput = document.getElementById('screenshot-input');
  const uploadZone = document.getElementById('upload-zone');
  const preview = document.getElementById('img-preview');
  const previewImg = document.getElementById('preview-img');

  if (fileInput && uploadZone) {
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) {
        previewImg.src = URL.createObjectURL(fileInput.files[0]);
        preview.classList.remove('hidden');
      }
    });

    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadZone.classList.remove('dragover');
      if (e.dataTransfer.files[0]) {
        fileInput.files = e.dataTransfer.files;
        previewImg.src = URL.createObjectURL(e.dataTransfer.files[0]);
        preview.classList.remove('hidden');
      }
    });
  }

  // Form submit
  document.getElementById('verify-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errEl = document.getElementById('verify-error');
    errEl.classList.add('hidden');

    const orderId = (orderIdInput ? orderIdInput.value : '').trim();
    const file = fileInput ? fileInput.files[0] : null;

    if (!orderId) {
      errEl.textContent = 'Please enter an Order ID or Verification Reference to verify.';
      errEl.classList.remove('hidden');
      return;
    }

    const btn = document.getElementById('verify-btn');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Verifying…';

    try {
      const fd = new FormData();
      fd.append('order_referral_code', orderId);
      if (file) fd.append('screenshot', file);

      const result = await api.crossVerify(fd);
      renderResult(result);
      loadHistory();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Verify Payment';
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
  const vTxId = r.verification_tx_id || (r.order_id ? `#${r.order_id}` : '—');
  const txEl = document.getElementById('res-verification-txid');
  if (txEl) txEl.textContent = vTxId;

  const copyBtn = document.getElementById('btn-copy-txid');
  if (copyBtn) {
    copyBtn.onclick = () => copyToClipboard(vTxId, copyBtn);
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
    `<div class="reason-item ${escapeAnalysisText(r.level)}"><span class="reason-icon">${icons[r.level] || '•'}</span><span>${escapeAnalysisText(r.text)}</span></div>`
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

  // NPCI Julian-Cycle Rail Audit
  const npci = r.npci_validation || (r.risk && r.risk.details && r.risk.details.npci_validation);
  const npciCard = document.getElementById('npci-card');
  if (npci && npciCard && npci.is_valid_format) {
    npciCard.classList.remove('hidden');
    const badgeEl = document.getElementById('npci-status-badge');
    const detailEl = document.getElementById('npci-detail-text');
    const yearEl = document.getElementById('npci-year-val');
    const julianEl = document.getElementById('npci-julian-val');
    const dateEl = document.getElementById('npci-date-val');
    const syncEl = document.getElementById('npci-sync-val');

    detailEl.textContent = npci.detail || '';
    yearEl.textContent = npci.decoded_year_digit != null ? `${npci.decoded_year_digit} (Claimed: ${npci.claimed_date ? npci.claimed_date.substring(0,4) : '—'})` : '—';
    julianEl.textContent = npci.decoded_julian_day != null ? `Day ${String(npci.decoded_julian_day).padStart(3, '0')}` : '—';
    dateEl.textContent = npci.decoded_date || 'Impossible Date';

    if (npci.verdict === 'valid') {
      badgeEl.innerHTML = '<span class="badge badge-genuine" style="font-weight:700;">✓ NPCI Rail Synced</span>';
      syncEl.innerHTML = '<span style="color:var(--color-ok); font-weight:700;">✓ Synced (Genuine Rail)</span>';
      npciCard.style.borderLeftColor = 'var(--color-ok)';
    } else if (npci.verdict === 'impossible_julian_day') {
      badgeEl.innerHTML = '<span class="badge badge-suspicious" style="font-weight:700;">✕ Impossible Julian Day</span>';
      syncEl.innerHTML = '<span style="color:var(--color-error); font-weight:700;">✕ Synthetic / Spoofed</span>';
      npciCard.style.borderLeftColor = 'var(--color-error)';
    } else if (npci.verdict === 'future_utr' || npci.verdict === 'year_mismatch') {
      badgeEl.innerHTML = '<span class="badge badge-suspicious" style="font-weight:700;">✕ Chronometric Anomaly</span>';
      syncEl.innerHTML = '<span style="color:var(--color-error); font-weight:700;">✕ Date Mismatch</span>';
      npciCard.style.borderLeftColor = 'var(--color-error)';
    } else if (npci.verdict === 'stale_utr') {
      badgeEl.innerHTML = '<span class="badge badge-careful" style="font-weight:700;">⚠️ Stale / Recycled UTR</span>';
      syncEl.innerHTML = '<span style="color:var(--color-warning); font-weight:700;">⚠️ Outdated Reference</span>';
      npciCard.style.borderLeftColor = 'var(--color-warning)';
    } else {
      badgeEl.innerHTML = '<span class="badge badge-neutral">Format Non-Standard</span>';
      syncEl.innerHTML = '<span style="color:var(--text-muted);">Non-standard Gateway</span>';
      npciCard.style.borderLeftColor = 'var(--line)';
    }
  } else if (npciCard) {
    npciCard.classList.add('hidden');
  }

  // Comparison table
  const ext = r.extracted_fields;
  const hasExtractedData = ext && (ext.amount != null || ext.tx_id || ext.payee_name || ext.date_str || ext.app_indicator);

  const grid = document.querySelector('.compare-grid');
  // Clear old rows beyond headers
  while (grid.children.length > 2) grid.removeChild(grid.lastChild);

  const headers = document.querySelectorAll('.compare-col-header');
  if (headers.length >= 2) {
    headers[0].textContent = 'Order Record (Expected)';
    headers[1].textContent = hasExtractedData ? 'Extracted from Screenshot' : 'Buyer Submission Status';
  }

  let rows = [];
  if (hasExtractedData) {
    rows = [
      { label: 'Amount', exp: formatCurrency(r.expected_amount), got: ext?.amount != null ? formatCurrency(ext.amount) : null, match: ext?.amount != null && Math.abs(ext.amount - r.expected_amount) < 0.01 },
      { label: 'Payee Name', exp: r.expected_payee_name || '—', got: ext?.payee_name || null, match: ext?.payee_name && r.expected_payee_name && ext.payee_name.toLowerCase().includes(r.expected_payee_name.toLowerCase().substring(0,5)) },
      { label: 'UPI ID (reference only; not checked)', exp: 'Not checked', got: ext?.payee_upi_id || null, match: null },
      { label: 'Transaction / UTR ID', exp: r.submitted_tx_id || '—', got: ext?.tx_id || ext?.utr || null, match: ext?.tx_id && r.submitted_tx_id && ext.tx_id.toUpperCase() === r.submitted_tx_id.toUpperCase() },
      { label: 'Payment Date', exp: '—', got: ext?.date_str || null, match: null },
      { label: 'Payment App', exp: '—', got: ext?.app_indicator || null, match: null },
      {
        label: 'NPCI Banking Rail',
        exp: 'NPCI 12-Digit Standard',
        got: npci && npci.is_valid_format ? (npci.verdict === 'valid' ? '✓ Verified Julian Cycle' : npci.verdict.replace(/_/g, ' ').toUpperCase()) : null,
        match: npci && npci.is_valid_format ? (npci.verdict === 'valid' ? true : false) : null
      },
    ];
  } else {
    rows = [
      { label: 'Order ID', exp: `#${r.order_id}`, got: 'Order Active', match: true },
      { label: 'Expected Amount', exp: formatCurrency(r.expected_amount), got: 'Awaiting buyer proof', match: null },
      { label: 'Payee Name', exp: r.expected_payee_name || '—', got: r.expected_payee_name || '—', match: true },
      { label: 'Payment Proof', exp: 'Screenshot Required', got: 'Upload screenshot above or await buyer upload', match: null },
    ];
  }

  rows.forEach(row => {
    const expCell = document.createElement('div');
    expCell.className = 'compare-cell';
    expCell.innerHTML = `<span style="font-size:0.72rem;color:var(--text-muted);display:block;">${escapeAnalysisText(row.label)}</span>${escapeAnalysisText(row.exp)}`;

    const gotCell = document.createElement('div');
    const gotText = row.got != null ? row.got : '<span class="unknown">Not detected</span>';
    const cls = row.got == null ? 'unknown' : row.match === true ? 'match' : row.match === false ? 'mismatch' : '';
    gotCell.className = `compare-cell ${cls}`;
    gotCell.innerHTML = row.got != null ? escapeAnalysisText(gotText) : gotText;

    grid.appendChild(expCell);
    grid.appendChild(gotCell);
  });

  renderSavedScreenshotAnalysis(r);

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

function renderSavedScreenshotAnalysis(result) {
  const card = document.getElementById('screenshot-analysis-card');
  if (!card) return;

  const forensics = result.forensics || {};
  const extracted = result.extracted_fields || result.extracted || {};
  const duplicates = result.duplicates || {};
  const imageMetadata = result.image_metadata || {};
  const hasScreenshotAnalysis = Boolean(
    Object.keys(forensics).length || Object.keys(extracted).length || Object.keys(imageMetadata).length
  );
  if (!hasScreenshotAnalysis) {
    card.classList.add('hidden');
    return;
  }
  card.classList.remove('hidden');

  const stats = [];
  const addStat = (label, value) => {
    if (value == null || value === '') return;
    stats.push(`<div class="analysis-stat"><span class="analysis-stat-label">${escapeAnalysisText(label)}</span><span class="analysis-stat-value">${escapeAnalysisText(value)}</span></div>`);
  };
  const duplicateStatus = (value) => {
    if (!value) return 'Not available';
    return value.duplicate_found ? 'Possible duplicate found' : 'No match detected';
  };
  const width = forensics.image_width;
  const height = forensics.image_height;
  if (width && height) addStat('Image dimensions', `${width} × ${height}`);
  const fileSize = imageMetadata.file_size_bytes ?? forensics.file_size_bytes;
  if (fileSize != null) addStat('Image size', `${Number(fileSize).toLocaleString()} bytes`);
  if (typeof forensics.has_exif === 'boolean') addStat('EXIF metadata', forensics.has_exif ? 'Present' : 'Not present');
  const software = forensics.exif_safe_fields?.Software;
  if (software) addStat('Editing software', software);
  if (forensics.ela_score != null) {
    const ela = Number(forensics.ela_score);
    addStat('Error Level Analysis', Number.isFinite(ela) ? ela.toFixed(2) : forensics.ela_score);
  }
  if (extracted.engine_used) addStat('OCR engine', extracted.engine_used);
  if (extracted.ocr_confidence != null) addStat('OCR confidence', `${Math.round(Number(extracted.ocr_confidence) * 100)}%`);
  if (extracted.viewpoint) addStat('Screenshot viewpoint', extracted.viewpoint);
  if (extracted.date_str) addStat('Payment date', extracted.date_str);
  if (extracted.time_str) addStat('Payment time', extracted.time_str);
  if (extracted.app_indicator) addStat('Payment app', extracted.app_indicator);
  if (duplicates.transaction_reference || duplicates.screenshot) {
    addStat('Transaction reference check', duplicateStatus(duplicates.transaction_reference));
    addStat('Screenshot duplicate check', duplicateStatus(duplicates.screenshot));
  }
  if (imageMetadata.sha256) addStat('SHA-256', imageMetadata.sha256);
  if (imageMetadata.phash) addStat('Perceptual hash', imageMetadata.phash);
  document.getElementById('analysis-stat-grid').innerHTML = stats.join('');

  const findings = Array.isArray(forensics.findings) ? forensics.findings : [];
  const findingsSection = document.getElementById('analysis-findings-section');
  findingsSection.classList.toggle('hidden', findings.length === 0);
  document.getElementById('analysis-findings').innerHTML = findings.map((finding) => {
    const level = finding.level ? `${String(finding.level).toUpperCase()}: ` : '';
    return `<li><strong>${escapeAnalysisText(level)}</strong>${escapeAnalysisText(finding.detail || finding.check || 'Image check completed.')}</li>`;
  }).join('');

  const observations = Array.isArray(forensics.observations) ? forensics.observations : [];
  const observationSection = document.getElementById('analysis-observations-section');
  observationSection.classList.toggle('hidden', observations.length === 0);
  document.getElementById('analysis-observations').innerHTML = observations
    .map(observation => `<li>${escapeAnalysisText(observation)}</li>`)
    .join('');
}

function escapeAnalysisText(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

async function loadHistory() {
  const el = document.getElementById('history-container');
  if (!el) return;
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
            <th>Order ID</th><th>Verification Ref</th><th>Bank Ref / UTR</th><th>Extracted Amount</th>
            <th>Verdict</th><th>Date</th>
          </tr></thead>
          <tbody>
            ${history.map(h => `
              <tr>
                <td>#${h.order_id}</td>
                <td class="mono" style="color:var(--accent-color);font-weight:600;">${h.verification_tx_id || '—'}</td>
                <td class="mono">${h.submitted_tx_id || h.extracted_tx_id || '—'}</td>
                <td>${h.extracted_amount != null ? formatCurrency(h.extracted_amount) : '—'}</td>
                <td>${verdictBadge(h.risk_verdict)}</td>
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
