/**
 * products.js — Products catalogue, photo certification, and reverse image verification
 */
(async () => {
  const user = await requireAuth();
  if (!user) return;
  initSidebar('products');

  let currentProducts = [];

  // DOM Elements
  const tbody = document.getElementById('products-tbody');
  const prodCountEl = document.getElementById('product-count');
  const toggleAddBtn = document.getElementById('toggle-add-btn');
  const addPanel = document.getElementById('add-product-panel');
  const closeAddBtn = document.getElementById('close-add-panel');
  const createForm = document.getElementById('create-product-form');
  const createError = document.getElementById('create-error');
  const saveProdBtn = document.getElementById('save-product-btn');

  // Ledger Elements
  const ledgerBadge = document.getElementById('ledger-badge');
  const ledgerStatusText = document.getElementById('ledger-status-text');
  const ledgerBlockCount = document.getElementById('ledger-block-count');

  // Certify Modal Elements
  const certifyModal = document.getElementById('certify-modal');
  const certifyModalTitle = document.getElementById('certify-modal-title');
  const certifyProdName = document.getElementById('certify-product-name');
  const closeCertifyBtn = document.getElementById('close-certify-modal');
  const certUploadForm = document.getElementById('cert-upload-form');
  const certProdIdInput = document.getElementById('cert-product-id');
  const certFileInput = document.getElementById('cert-file-input');
  const certUploadZone = document.getElementById('cert-upload-zone');
  const certPreview = document.getElementById('cert-preview');
  const certPreviewImg = document.getElementById('cert-preview-img');
  const certSubmitBtn = document.getElementById('cert-submit-btn');
  const certUploadError = document.getElementById('cert-upload-error');
  const certResultBox = document.getElementById('cert-result-box');

  // Verify Elements
  const verifyImgForm = document.getElementById('verify-img-form');
  const verifyFileInput = document.getElementById('verify-file-input');
  const verifyUploadZone = document.getElementById('verify-upload-zone');
  const verifyPreview = document.getElementById('verify-preview');
  const verifyPreviewImg = document.getElementById('verify-preview-img');
  const verifyImgBtn = document.getElementById('verify-img-btn');
  const verifyResultBox = document.getElementById('verify-result-box');
  const verifyVerdictBadge = document.getElementById('verify-verdict-badge');
  const verifyResultMsg = document.getElementById('verify-result-msg');
  const verifyMatchDetails = document.getElementById('verify-match-details');

  // -------------------------------------------------------------
  // 1. Load Ledger Integrity Status
  // -------------------------------------------------------------
  async function loadLedgerStatus() {
    try {
      const res = await api.ledgerStatus();
      if (res.valid) {
        ledgerBadge.className = 'badge badge-confirmed';
        ledgerBadge.textContent = 'Chain Valid ✓';
        ledgerStatusText.textContent = `All cryptographic links verified. Genesis: ${res.genesis_present ? 'Present' : 'None'}.`;
      } else {
        ledgerBadge.className = 'badge badge-cancelled';
        ledgerBadge.textContent = 'Integrity Issue ⚠️';
        ledgerStatusText.textContent = `Ledger integrity failed: ${res.broken_at_entry_id ? 'Broken block #' + res.broken_at_entry_id : 'Verification error'}`;
      }
      ledgerBlockCount.textContent = res.total_entries;
    } catch (err) {
      ledgerBadge.className = 'badge badge-cancelled';
      ledgerBadge.textContent = 'Check Failed';
      ledgerStatusText.textContent = 'Could not fetch ledger status.';
    }
  }

  // -------------------------------------------------------------
  // 2. Load Products Catalogue
  // -------------------------------------------------------------
  async function loadProducts() {
    try {
      currentProducts = await api.getProducts();
      prodCountEl.textContent = currentProducts.length;

      if (!currentProducts || currentProducts.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align:center;padding:2.5rem;color:var(--text-secondary);">
              No products yet. Click <strong>+ New Product</strong> above to register your first product.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = currentProducts.map(p => `
        <tr>
          <td>
            <div style="font-weight:600;color:var(--text-primary);">${escapeHtml(p.name)}</div>
            ${p.description ? `<div style="font-size:0.8rem;color:var(--text-muted);">${escapeHtml(p.description)}</div>` : ''}
          </td>
          <td style="font-weight:500;">${formatCurrency(p.price)}</td>
          <td>
            <span class="badge ${p.certificate_count > 0 ? 'badge-confirmed' : 'badge-pending'}">
              ${p.certificate_count} certified
            </span>
          </td>
          <td style="font-size:0.85rem;color:var(--text-secondary);">${formatDate(p.created_at)}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="openCertifyModal(${p.id})">
              📸 Certify Photo
            </button>
          </td>
        </tr>
      `).join('');
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align:center;padding:2rem;color:var(--color-error);">
            Failed to load products: ${escapeHtml(err.message)}
          </td>
        </tr>
      `;
    }
  }

  // -------------------------------------------------------------
  // 3. Add Product Actions
  // -------------------------------------------------------------
  toggleAddBtn.addEventListener('click', () => {
    addPanel.classList.toggle('hidden');
    if (!addPanel.classList.contains('hidden')) {
      document.getElementById('prod-name').focus();
    }
  });

  closeAddBtn.addEventListener('click', () => {
    addPanel.classList.add('hidden');
    createError.classList.add('hidden');
    createForm.reset();
  });

  createForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    createError.classList.add('hidden');

    const name = document.getElementById('prod-name').value.trim();
    const priceVal = parseFloat(document.getElementById('prod-price').value);
    const description = document.getElementById('prod-desc').value.trim();

    if (!name) {
      showError(createError, 'Please enter a product name.');
      return;
    }
    if (isNaN(priceVal) || priceVal < 0) {
      showError(createError, 'Please enter a valid price.');
      return;
    }

    saveProdBtn.disabled = true;
    saveProdBtn.textContent = 'Saving...';

    try {
      await api.createProduct({ name, price: priceVal, description });
      showToast('Product created successfully', 'ok');
      createForm.reset();
      addPanel.classList.add('hidden');
      await loadProducts();
      await loadLedgerStatus();
    } catch (err) {
      showError(createError, err.message);
    } finally {
      saveProdBtn.disabled = false;
      saveProdBtn.textContent = 'Create Product';
    }
  });

  // -------------------------------------------------------------
  // 4. Certify Photo Modal
  // -------------------------------------------------------------
  window.openCertifyModal = (productId) => {
    const prod = currentProducts.find(p => p.id === productId);
    if (!prod) return;

    certProdIdInput.value = productId;
    certModalTitle.textContent = `Certify Photo: ${prod.name}`;
    certProdName.textContent = `Product ID #${prod.id} · Price: ${formatCurrency(prod.price)}`;
    certUploadError.classList.add('hidden');
    certResultBox.classList.add('hidden');
    certUploadForm.reset();
    certPreview.classList.add('hidden');
    certModal.classList.remove('hidden');
    certModal.scrollIntoView({ behavior: 'smooth' });
  };

  closeCertifyBtn.addEventListener('click', () => {
    certModal.classList.add('hidden');
  });

  // Drag & drop for cert upload
  setupDragDrop(certUploadZone, certFileInput, certPreview, certPreviewImg);

  certUploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    certUploadError.classList.add('hidden');
    certResultBox.classList.add('hidden');

    const file = certFileInput.files[0];
    const productId = certProdIdInput.value;

    if (!file) {
      showError(certUploadError, 'Please select an image to upload.');
      return;
    }

    const fd = new FormData();
    fd.append('file', file);

    certSubmitBtn.disabled = true;
    certSubmitBtn.textContent = 'Computing Hashes & Ledger Entry...';

    try {
      const cert = await api.uploadCertificate(productId, fd);
      showToast('Photo certified and recorded in ledger!', 'ok');

      // Fill in result
      document.getElementById('res-cert-id').textContent = cert.certificate_id;
      document.getElementById('res-cert-dims').textContent = `${cert.image_width || '?'}×${cert.image_height || '?'} px (${(cert.file_size_bytes / 1024).toFixed(1)} KB)`;
      document.getElementById('res-cert-sha').textContent = cert.sha256_hash;
      document.getElementById('res-cert-phash').textContent = cert.phash || 'N/A';

      certResultBox.classList.remove('hidden');
      await loadProducts();
      await loadLedgerStatus();
    } catch (err) {
      showError(certUploadError, err.message);
    } finally {
      certSubmitBtn.disabled = false;
      certSubmitBtn.textContent = 'Compute Fingerprint & Add to Ledger';
    }
  });

  // -------------------------------------------------------------
  // 5. Reverse Image Verification
  // -------------------------------------------------------------
  setupDragDrop(verifyUploadZone, verifyFileInput, verifyPreview, verifyPreviewImg);

  verifyImgForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const file = verifyFileInput.files[0];
    if (!file) {
      showToast('Please select an image to verify', 'error');
      return;
    }

    const fd = new FormData();
    fd.append('file', file);

    verifyImgBtn.disabled = true;
    verifyImgBtn.textContent = 'Comparing Fingerprints...';

    try {
      const res = await api.verifyCertificate(fd);
      verifyResultBox.classList.remove('hidden');

      if (res.match_type === 'exact') {
        verifyVerdictBadge.className = 'risk-verdict-badge verdict-genuine';
        verifyVerdictBadge.textContent = 'Exact Certified Match ✓';
        verifyResultMsg.textContent = res.message;
        fillMatchDetails(res.certificate, true, res.phash_distance);
      } else if (res.match_type === 'similar') {
        verifyVerdictBadge.className = 'risk-verdict-badge verdict-careful';
        verifyVerdictBadge.textContent = 'Perceptually Similar ⚠️';
        verifyResultMsg.textContent = res.message;
        fillMatchDetails(res.certificate, false, res.phash_distance);
      } else {
        verifyVerdictBadge.className = 'risk-verdict-badge verdict-suspicious';
        verifyVerdictBadge.textContent = 'No Match Found ✕';
        verifyResultMsg.textContent = res.message;
        verifyMatchDetails.classList.add('hidden');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      verifyImgBtn.disabled = false;
      verifyImgBtn.textContent = 'Verify Against Certified Images';
    }
  });

  function fillMatchDetails(cert, isExact, phashDist) {
    if (!cert) {
      verifyMatchDetails.classList.add('hidden');
      return;
    }
    verifyMatchDetails.classList.remove('hidden');
    document.getElementById('match-cert-id').textContent = cert.certificate_id;
    document.getElementById('match-cert-file').textContent = cert.filename || 'Certified photo';
    document.getElementById('match-sha-status').textContent = isExact ? 'Exact Match (100% Identical Bytes)' : 'Different (Modified or Recompressed)';
    document.getElementById('match-phash-dist').textContent = phashDist !== null && phashDist !== undefined ? `${phashDist} (Threshold: 10)` : 'N/A';
  }

  // -------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------
  function setupDragDrop(zone, input, previewBox, previewImg) {
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (e.dataTransfer.files[0]) {
        input.files = e.dataTransfer.files;
        showPreview(e.dataTransfer.files[0], previewBox, previewImg);
      }
    });
    input.addEventListener('change', () => {
      if (input.files[0]) showPreview(input.files[0], previewBox, previewImg);
    });
  }

  function showPreview(file, previewBox, previewImg) {
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImg.src = e.target.result;
      previewBox.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
  }

  function showError(el, msg) {
    el.textContent = msg;
    el.classList.remove('hidden');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, (m) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[m]));
  }

  // Initial load
  await Promise.all([loadProducts(), loadLedgerStatus()]);
})();
