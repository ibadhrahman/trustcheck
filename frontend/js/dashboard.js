/** dashboard.js */
(async () => {
  const user = await requireAuth();
  if (!user) return;
  initSidebar('dashboard');

  // Load stats
  try {
    const stats = await api.dashboardStats();
    if (document.getElementById('stat-total')) document.getElementById('stat-total').textContent = stats.total_orders;
    if (document.getElementById('stat-pending')) document.getElementById('stat-pending').textContent = stats.pending_orders;
    if (document.getElementById('stat-review')) document.getElementById('stat-review').textContent = stats.needs_review_orders;
    if (document.getElementById('stat-confirmed')) document.getElementById('stat-confirmed').textContent = stats.confirmed_orders;
    if (document.getElementById('stat-suspicious')) document.getElementById('stat-suspicious').textContent = stats.suspicious_submissions;
  } catch (e) {
    showToast('Could not load stats: ' + e.message, 'error');
  }

  // Load recent verifications (seller-only forensic details)
  await loadVerifications();

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
      payment_submitted_by_buyer: '📤',
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

async function loadVerifications() {
  const el = document.getElementById('verifications-list');
  try {
    const history = await api.paymentHistory(8);
    if (!history || !history.length) {
      el.innerHTML = '<div class="empty-state" style="padding:1.5rem;"><p>No payment verifications yet. <a href="/verify-payment.html">Verify a payment</a> to see the analysis here.</p></div>';
      return;
    }

    el.innerHTML = history.map(h => {
      const verdict = h.risk_verdict || 'unknown';
      const verdictColors = { genuine: 'var(--color-ok)', careful: '#f59e0b', suspicious: 'var(--color-error)', unknown: 'var(--text-muted)' };
      const verdictBg = { genuine: 'var(--color-ok-bg)', careful: 'rgba(245,158,11,0.1)', suspicious: 'rgba(239,68,68,0.1)', unknown: 'transparent' };
      const verdictIcons = { genuine: '✅', careful: '⚠️', suspicious: '🚨', unknown: '❓' };
      const extracted = h.extracted_fields || {};
      const comparison = h.comparison || {};
      const forensics = h.forensics || {};
      const duplicates = h.duplicates || {};
      const hasForensics = Boolean(h.forensics && Object.keys(h.forensics).length);
      const hasDuplicateResults = Boolean(h.duplicates);
      const txDuplicate = duplicates.transaction_reference || {};
      const imageDuplicate = duplicates.screenshot || {};
      const hasDuplicate = Boolean(txDuplicate.duplicate_found || imageDuplicate.duplicate_found);
      const amountValue = extracted.amount ?? h.extracted_amount;
      const payeeValue = extracted.payee_name || h.extracted_payee_name;
      const txRef = h.submitted_tx_id || extracted.tx_id || extracted.utr || h.extracted_tx_id;
      const safe = (value) => escapeHtml(value == null || value === '' ? '—' : String(value));
      const expectedAmount = comparison.expected_amount;
      const expectedPayee = comparison.expected_payee_name;
      const fieldLine = (label, expected, actual, matches, isAmount = false) => {
        const shownExpected = isAmount && expected != null ? formatCurrency(expected) : expected;
        const shownActual = isAmount && actual != null ? formatCurrency(actual) : actual;
        const state = actual == null ? 'Not detected' : expected == null ? 'Not compared' : matches === true ? 'Match' : matches === false ? 'Mismatch' : 'Not compared';
        const stateColor = state === 'Match' ? 'var(--color-ok)' : state === 'Mismatch' ? 'var(--color-error)' : 'var(--text-muted)';
        return `<li><strong>${safe(label)}:</strong> ${safe(shownActual)} <span style="color:var(--text-muted);">(expected ${safe(shownExpected)})</span> — <span style="color:${stateColor};">${state}</span></li>`;
      };

      const exifWarning = (forensics.findings || []).find(f => f.check === 'exif_software' && f.level === 'warning');
      const exifSoftware = forensics.exif_safe_fields?.Software;
      const elaFinding = (forensics.findings || []).find(f => f.check === 'ela');
      const imageCheck = !h.has_screenshot
        ? 'No screenshot was provided.'
        : !hasForensics
          ? 'Detailed image checks were not saved for this older verification.'
          : exifWarning
            ? `Editing software detected in EXIF: ${exifSoftware || 'unknown software'}.`
            : 'No known editing software detected in EXIF.';
      const elaSummary = !h.has_screenshot
        ? ''
        : !hasForensics
          ? ''
          : elaFinding?.detail || (forensics.ela_score != null ? `ELA score: ${Number(forensics.ela_score).toFixed(2)}.` : 'ELA check unavailable.');
      const duplicateLine = (label, result) => {
        if (result.duplicate_found) return `<li><strong>${safe(label)}:</strong> <span style="color:var(--color-error);">Duplicate detected</span> — ${safe(result.message || 'Previous match found.')}</li>`;
        const status = hasDuplicateResults ? 'No match detected' : 'Not available for this older verification';
        return `<li><strong>${safe(label)}:</strong> ${status}</li>`;
      };
      const amount = amountValue != null ? formatCurrency(amountValue) : 'Not detected';
      const reviewNotes = (h.reasons || []).filter(r => r.level === 'warning' || r.level === 'error');
      const notesHtml = reviewNotes.length
        ? `<p style="margin:.55rem 0 0;color:var(--text-secondary);"><strong>Review:</strong> ${reviewNotes.map(r => safe(r.text)).join(' ')}</p>`
        : '';

      return `
        <div style="border:1px solid var(--border-color);border-radius:8px;padding:1rem 1.1rem;margin-bottom:0.75rem;background:var(--surface);">
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;margin-bottom:0.6rem;">
            <div style="display:flex;align-items:center;gap:0.6rem;">
              <span style="font-size:1rem;background:${verdictBg[verdict]};color:${verdictColors[verdict]};border:1px solid ${verdictColors[verdict]};border-radius:6px;padding:0.2rem 0.65rem;font-weight:700;font-size:0.8rem;text-transform:uppercase;letter-spacing:0.04em;">
                ${verdictIcons[verdict]} ${verdict}
              </span>
              <span style="font-size:0.85rem;font-weight:600;color:var(--text-primary);">Score: ${safe(h.risk_score)}</span>
              ${hasDuplicate ? '<span style="background:rgba(239,68,68,0.15);color:var(--color-error);font-size:0.7rem;padding:0.15rem 0.5rem;border-radius:4px;font-weight:600;">⚠️ Duplicate detected</span>' : ''}
            </div>
            <span style="font-size:0.75rem;color:var(--text-muted);">${safe(formatDate(h.created_at))}</span>
          </div>

          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:0.5rem 1rem;font-size:0.82rem;">
            <div><span style="color:var(--text-muted);display:block;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;">Order</span><strong>#${safe(h.order_id)}</strong></div>
            <div><span style="color:var(--text-muted);display:block;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;">Amount Extracted</span>${safe(amount)}</div>
            <div><span style="color:var(--text-muted);display:block;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;">Payee Name</span>${safe(payeeValue)}</div>
            <div><span style="color:var(--text-muted);display:block;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;">Tx Ref</span><span class="mono" style="font-size:0.78rem;">${safe(txRef)}</span></div>
            <div><span style="color:var(--text-muted);display:block;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;">Viewpoint</span>${safe(extracted.viewpoint || h.screenshot_viewpoint)}</div>
            <div><span style="color:var(--text-muted);display:block;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;">Verification ID</span><span class="mono" style="font-size:0.75rem;color:var(--accent-color);">${safe(h.verification_tx_id)}</span></div>
          </div>

          <details style="margin-top:.85rem;border-top:1px solid var(--border-color);padding-top:.7rem;">
            <summary style="cursor:pointer;font-weight:600;color:var(--accent-color);">Analysis details</summary>
            <div style="margin-top:.65rem;font-size:.82rem;color:var(--text-primary);">
              <ul style="padding-left:1.2rem;line-height:1.8;">
                ${fieldLine('Amount', expectedAmount, amountValue, comparison.amount_match, true)}
                ${fieldLine('Payee', expectedPayee, payeeValue, comparison.payee_name_match)}
                <li><strong>UPI ID seen:</strong> ${safe(extracted.payee_upi_id)} <span style="color:var(--text-muted);">(reference only; not checked)</span></li>
                <li><strong>Image / EXIF:</strong> ${safe(imageCheck)}${elaSummary ? ` <span style="color:var(--text-muted);">${safe(elaSummary)}</span>` : ''}</li>
                ${duplicateLine('Screenshot duplicate', imageDuplicate)}
                ${duplicateLine('Transaction reference duplicate', txDuplicate)}
              </ul>
              ${notesHtml}
              <p style="font-size:.75rem;color:var(--text-muted);margin-top:.6rem;">Risk estimate only — not proof of payment.</p>
            </div>
          </details>
        </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">Could not load verifications: ${e.message}</div>`;
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}
