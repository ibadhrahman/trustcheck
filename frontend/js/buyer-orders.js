(() => {
  const lookupForm = document.getElementById('order-lookup-form');
  const codeInput = document.getElementById('buyer-access-code');
  const lookupError = document.getElementById('lookup-error');
  const resultSection = document.getElementById('order-result');
  const orderContainer = document.getElementById('buyer-orders-container');
  let activeAccessCode = '';

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  function referenceFromInput(value) {
    const raw = String(value || '').trim();
    try {
      const parsed = new URL(raw, window.location.origin);
      const hashParams = new URLSearchParams(parsed.hash.replace(/^#/, ''));
      const code = hashParams.get('claim')
        || parsed.searchParams.get('claim')
        || hashParams.get('ref')
        || parsed.searchParams.get('ref');
      if (code) return code.trim();
      const rawHash = parsed.hash.replace(/^#/, '').trim();
      if (rawHash && !rawHash.includes('=') && rawHash.length >= 8) return rawHash;
    } catch (_) { /* The user may have pasted a raw reference instead of a URL. */ }
    return raw;
  }

  async function buyerFetch(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (activeAccessCode) headers['X-Buyer-Access-Code'] = activeAccessCode;
    if (!(options.body instanceof FormData) && options.body) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, { ...options, headers, cache: 'no-store' });
    const data = response.headers.get('content-type')?.includes('application/json') ? await response.json() : {};
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  lookupForm.addEventListener('submit', async event => {
    event.preventDefault();
    lookupError.classList.add('hidden');
    activeAccessCode = referenceFromInput(codeInput.value);
    if (activeAccessCode.length < 8) {
      lookupError.textContent = 'Enter the order reference your seller shared (e.g. TXN-PCFY-4A5K).';
      lookupError.classList.remove('hidden');
      return;
    }
    const button = document.getElementById('lookup-order-button');
    button.disabled = true;
    button.textContent = 'Checking…';
    try {
      const order = await buyerFetch('/api/buyer/order/lookup', {
        method: 'POST',
        body: JSON.stringify({ access_code: activeAccessCode }),
      });
      if (window.location.hash) history.replaceState(null, '', window.location.pathname + window.location.search);
      resultSection.classList.remove('hidden');
      renderOrder(order);
    } catch (error) {
      activeAccessCode = '';
      resultSection.classList.add('hidden');
      lookupError.textContent = error.message;
      lookupError.classList.remove('hidden');
    } finally {
      button.disabled = false;
      button.textContent = 'Find order';
    }
  });

  document.getElementById('clear-order').addEventListener('click', () => {
    activeAccessCode = '';
    codeInput.value = '';
    lookupError.classList.add('hidden');
    resultSection.classList.add('hidden');
    orderContainer.replaceChildren();
  });

  function statusLabel(status) {
    const labels = {
      pending: 'Awaiting seller payment confirmation',
      needs_review: 'Seller is reviewing the payment',
      seller_confirmed: 'Seller confirmed bank credit',
      cancelled: 'Order cancelled',
    };
    return labels[status] || String(status || 'Status unavailable').replaceAll('_', ' ');
  }

  function renderOrder(order) {
    const outcomeContent = order.outcome
      ? renderOutcome(order)
      : (order.can_submit_outcome ? outcomeForm(order, false) : '');
    const nextStep = order.can_submit_outcome
      ? ''
      : '<p class="text-sm text-muted" style="margin-top:.75rem;">You can submit an outcome after the seller confirms bank credit. If the item never arrives, choose “Order not received” once reporting is available.</p>';
    orderContainer.innerHTML = `
      <article class="buyer-card">
        <div style="display:flex;justify-content:space-between;gap:.75rem;flex-wrap:wrap;">
          <div>
            <h2 style="font-size:1.1rem;margin:0;">${escapeHtml(order.item || 'Order')}</h2>
            <div class="text-sm text-muted">Order #${escapeHtml(order.id)} · ${escapeHtml(order.seller_name || 'Seller')} · ${formatCurrency(order.expected_amount)}</div>
          </div>
          <span class="badge ${order.status === 'seller_confirmed' ? 'badge-confirmed' : order.status === 'cancelled' ? 'badge-suspicious' : 'badge-pending'}">${escapeHtml(statusLabel(order.status))}</span>
        </div>
        ${nextStep}
        ${outcomeContent}
      </article>`;

    orderContainer.querySelectorAll('.outcome-form').forEach(form => {
      form.querySelectorAll('input[name="outcome"]').forEach(radio => radio.addEventListener('change', () => updateReceiptRequirement(form)));
      form.querySelector('select[name="reason"]').addEventListener('change', () => updateReceiptRequirement(form));
      form.addEventListener('submit', submitOutcome);
      updateReceiptRequirement(form);
    });
    orderContainer.querySelectorAll('[data-resolution]').forEach(button => button.addEventListener('click', submitDecision));
  }

  function updateReceiptRequirement(form) {
    const selected = form.querySelector('input[name="outcome"]:checked');
    const reason = form.elements.reason?.value;
    const received = form.elements.confirmed_received;
    const notReceivedConfirmation = form.elements.confirmed_not_received;
    const receivedLabel = form.querySelector('.received-confirmation');
    const notReceivedLabel = form.querySelector('.not-received-confirmation');
    const problem = selected?.value === 'report_problem';
    const details = form.querySelector('.problem-details');
    details.classList.toggle('hidden', !problem);
    form.elements.reason.required = problem;
    form.elements.description.required = problem;
    const notReceived = selected?.value === 'report_problem' && reason === 'not_received';
    receivedLabel.classList.toggle('hidden', notReceived);
    notReceivedLabel.classList.toggle('hidden', !notReceived);
    received.required = !notReceived;
    notReceivedConfirmation.required = notReceived;
    if (notReceived) received.checked = false;
    else notReceivedConfirmation.checked = false;
  }

  function outcomeForm(order, laterReport) {
    return `<form class="outcome-form buyer-outcome-form" enctype="multipart/form-data">
      <fieldset style="border:0;padding:0;margin:0;">
        <legend><strong>${laterReport ? 'Do you need to report another problem?' : 'What happened with your order?'}</strong></legend>
        ${!laterReport ? `<label class="buyer-choice"><input type="radio" name="outcome" value="received_as_described" required><span><strong>Received as described</strong><br><small class="text-muted">This does not flag the seller. You may add a product photo.</small></span></label>` : ''}
        <label class="buyer-choice"><input type="radio" name="outcome" value="report_problem" ${laterReport ? 'checked required' : 'required'}><span><strong>Report an order problem</strong><br><small class="text-muted">The seller will be notified and can offer a resolution.</small></span></label>
      </fieldset>
      <label class="buyer-choice received-confirmation"><input type="checkbox" name="confirmed_received" required><span><strong>I have received this order</strong><br><small class="text-muted">Required for a positive update or an issue with an item that arrived.</small></span></label>
      <label class="buyer-choice not-received-confirmation hidden"><input type="checkbox" name="confirmed_not_received" required><span><strong>I confirm this order has not arrived</strong><br><small class="text-muted">The seller will be notified about the missing delivery.</small></span></label>
      <div class="problem-details ${laterReport ? '' : 'hidden'}">
        <div class="form-group"><label class="form-label">What went wrong?</label><select class="form-input" name="reason"><option value="">Choose a reason</option><option value="not_received">Order not received</option><option value="wrong_item">Wrong item</option><option value="damaged_item">Damaged item</option><option value="missing_item">Missing item</option><option value="not_as_described">Not as described</option></select></div>
        <div class="form-group"><label class="form-label">Description</label><textarea class="form-input" name="description" maxlength="2000" rows="3" placeholder="Describe the issue"></textarea></div>
      </div>
      <div class="form-group"><label class="form-label">Photo (optional)</label><input class="form-input" type="file" name="photo" accept="image/jpeg,image/png,image/webp"><small class="text-muted">JPEG, PNG, or WebP, up to 5 MB. Photos stay private to you and the seller.</small></div>
      <button class="btn btn-primary btn-sm" type="submit">${laterReport ? 'Submit problem report' : 'Submit order update'}</button>
      <div class="form-message text-sm" role="status" style="margin-top:.5rem;"></div>
    </form>`;
  }

  function renderOutcome(order) {
    const outcome = order.outcome;
    const problem = outcome.outcome === 'problem';
    return `<section style="margin-top:1rem;padding-top:.9rem;border-top:1px solid var(--line);">
      <strong>${problem ? 'Order problem reported' : 'Received as described'}</strong>
      ${problem ? `<p class="text-sm" style="margin:.45rem 0;"><strong>${escapeHtml((outcome.reason || '').replaceAll('_', ' '))}</strong><br>${escapeHtml(outcome.description || '')}</p>` : '<p class="text-sm text-muted">Your positive confirmation does not flag the seller.</p>'}
      ${problem && outcome.seller_response ? `<div class="alert alert-info" style="margin:.65rem 0;"><strong>Seller offer: ${escapeHtml((outcome.seller_resolution_type || '').replaceAll('_', ' '))}</strong><br>${escapeHtml(outcome.seller_response)}</div>` : ''}
      ${problem && outcome.status === 'resolution_offered' ? `<div style="display:flex;gap:.5rem;flex-wrap:wrap;margin:.65rem 0;"><button type="button" class="btn btn-success btn-sm" data-resolution="true">Confirm resolved</button><button type="button" class="btn btn-secondary btn-sm" data-resolution="false">Still unresolved</button></div>` : ''}
      ${problem && outcome.status === 'resolved' ? '<p class="text-sm text-success">You confirmed this issue was resolved.</p>' : ''}
      <h3 class="text-sm" style="margin:.85rem 0 .35rem;">History</h3>
      ${(outcome.events || []).map(event => `<div class="text-xs" style="padding:.45rem 0;border-top:1px solid var(--line);"><strong>${escapeHtml(event.event_type.replaceAll('_', ' '))}</strong> · ${formatDate(event.created_at)}${event.resolution_type ? ` · ${escapeHtml(event.resolution_type)}` : ''}${event.message ? `<div style="white-space:pre-wrap;margin-top:.2rem;">${escapeHtml(event.message)}</div>` : ''}${(event.evidence_ids || []).map(id => `<button type="button" class="btn btn-ghost btn-sm" data-evidence="${id}">View private photo</button>`).join(' ')}</div>`).join('')}
      ${!problem && order.can_submit_outcome ? outcomeForm(order, true) : ''}
    </section>`;
  }

  async function submitOutcome(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = form.querySelector('.form-message');
    const data = new FormData(form);
    const selected = form.querySelector('input[name="outcome"]:checked');
    if (!selected) return;
    if (selected.value === 'report_problem' && (!form.elements.reason.value || !form.elements.description.value.trim())) {
      message.textContent = 'Choose a reason and describe the problem.';
      message.className = 'form-message text-sm text-danger';
      return;
    }
    try {
      await buyerFetch('/api/buyer/order/outcome', { method: 'POST', body: data });
      showToast(selected.value === 'report_problem' ? 'Problem report sent to the seller.' : 'Order update saved.', 'ok');
      await reloadOrder();
    } catch (error) {
      message.textContent = error.message;
      message.className = 'form-message text-sm text-danger';
    }
  }

  async function submitDecision(event) {
    const resolved = event.currentTarget.dataset.resolution === 'true';
    const message = resolved ? null : window.prompt('Optional: tell the seller why the issue is still unresolved.') || null;
    try {
      await buyerFetch('/api/buyer/order/outcome/resolution', {
        method: 'POST', body: JSON.stringify({ resolved, message }),
      });
      showToast(resolved ? 'You confirmed the issue was resolved.' : 'The report remains unresolved.', 'ok');
      await reloadOrder();
    } catch (error) { showToast(error.message, 'error'); }
  }

  async function reloadOrder() {
    const order = await buyerFetch('/api/buyer/order/lookup', {
      method: 'POST', body: JSON.stringify({ access_code: activeAccessCode }),
    });
    renderOrder(order);
  }

  orderContainer.addEventListener('click', async event => {
    const button = event.target.closest('[data-evidence]');
    if (!button) return;
    try {
      const response = await fetch(`/api/buyer/order/evidence/${button.dataset.evidence}`, {
        headers: { 'X-Buyer-Access-Code': activeAccessCode }, cache: 'no-store',
      });
      if (!response.ok) throw new Error('Could not load this private photo.');
      const url = URL.createObjectURL(await response.blob());
      const view = document.createElement('div');
      view.style.cssText = 'position:fixed;inset:0;background:rgba(10,15,28,.88);z-index:9999;display:grid;place-items:center;padding:1rem;';
      view.innerHTML = '<button class="btn btn-secondary" style="position:absolute;right:1rem;top:1rem;">Close</button><img alt="Private order photo" style="max-width:95vw;max-height:90vh;object-fit:contain;border-radius:12px;">';
      view.querySelector('img').src = url;
      view.querySelector('button').onclick = () => { URL.revokeObjectURL(url); view.remove(); };
      view.onclick = e => { if (e.target === view) { URL.revokeObjectURL(url); view.remove(); } };
      document.body.appendChild(view);
    } catch (error) { showToast(error.message, 'error'); }
  });

  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const searchParams = new URLSearchParams(window.location.search);
  const rawHash = window.location.hash.replace(/^#/, '').trim();
  const claim = hashParams.get('claim')
    || searchParams.get('claim')
    || hashParams.get('ref')
    || searchParams.get('ref')
    || (rawHash && !rawHash.includes('=') && rawHash.length >= 8 ? rawHash : null);
  if (claim) {
    codeInput.value = claim;
    history.replaceState(null, '', window.location.pathname);
    lookupForm.requestSubmit();
  }
})();
