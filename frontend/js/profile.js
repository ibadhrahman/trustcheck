/**
 * profile.js — Seller Profile & Settings management
 */
(async () => {
  const user = await requireAuth();
  if (!user) return;
  initSidebar('profile');

  // DOM Elements
  const sellerCodeDisplay = document.getElementById('seller-code-display');
  const shareableBioText = document.getElementById('shareable-bio-text');
  const copySellerCodeBtn = document.getElementById('copy-seller-code-btn');
  const copyBioBtn = document.getElementById('copy-bio-btn');

  const profileForm = document.getElementById('profile-form');
  const profileError = document.getElementById('profile-error');
  const saveBtn = document.getElementById('save-profile-btn');

  const bizNameInput = document.getElementById('prof-biz-name');
  const contactNameInput = document.getElementById('prof-contact-name');
  const upiInput = document.getElementById('prof-upi');
  const phoneInput = document.getElementById('prof-phone');
  const emailInput = document.getElementById('prof-email');
  const addressInput = document.getElementById('prof-address');
  const notesInput = document.getElementById('prof-notes');

  const accEmail = document.getElementById('acc-email');
  const accId = document.getElementById('acc-id');
  const accCreated = document.getElementById('acc-created');

  let currentSellerCode = '';

  // 1. Populate Account Details
  if (user && user.user) {
    if (user.user.email) {
      const accountEmailLink = document.createElement('a');
      accountEmailLink.href = `mailto:${user.user.email}`;
      accountEmailLink.textContent = user.user.email;
      accEmail.replaceChildren(accountEmailLink);
    } else {
      accEmail.textContent = '—';
    }
    accId.textContent = `#${user.user.id}`;
    accCreated.textContent = formatDate(user.user.created_at);
  }

  // 2. Fetch Seller Referral Code
  async function loadSellerCode() {
    try {
      const res = await api.getSellerCode();
      currentSellerCode = res.seller_referral_code || '';
      sellerCodeDisplay.textContent = currentSellerCode;
      shareableBioText.textContent = `Official TrustCheck Verified Seller Code: ${currentSellerCode} · Verify orders at ${window.location.origin}`;
      copySellerCodeBtn.disabled = !currentSellerCode;
      copyBioBtn.disabled = !currentSellerCode;
    } catch (err) {
      sellerCodeDisplay.textContent = 'Error loading code';
      shareableBioText.textContent = 'Could not load the seller code. Please try again.';
    }
  }

  // 3. Fetch and Populate Profile
  async function loadProfile() {
    try {
      const prof = await api.getProfile();
      bizNameInput.value = prof.business_name || '';
      contactNameInput.value = prof.contact_name || '';
      upiInput.value = prof.upi_id || '';
      phoneInput.value = prof.contact_phone || '';
      emailInput.value = prof.contact_email || '';
      addressInput.value = prof.business_address || '';
      notesInput.value = prof.notes || '';
    } catch (err) {
      showError(profileError, 'Failed to load profile: ' + err.message);
    }
  }

  // 4. Copy Handlers
  copySellerCodeBtn.addEventListener('click', () => {
    if (!currentSellerCode) return;
    copyToClipboard(currentSellerCode, copySellerCodeBtn);
  });

  copyBioBtn.addEventListener('click', () => {
    if (!currentSellerCode) return;
    copyToClipboard(shareableBioText.textContent, copyBioBtn);
  });

  // 5. Save Profile Form
  profileForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    profileError.classList.add('hidden');

    const business_name = bizNameInput.value.trim();
    const upi_id = upiInput.value.trim();

    if (!business_name) {
      showError(profileError, 'Please enter a business or brand name.');
      return;
    }
    if (!upi_id) {
      showError(profileError, 'Please enter your business UPI ID.');
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving Changes...';

    const payload = {
      business_name,
      contact_name: contactNameInput.value.trim() || null,
      upi_id,
      contact_phone: phoneInput.value.trim() || null,
      contact_email: emailInput.value.trim() || null,
      business_address: addressInput.value.trim() || null,
      notes: notesInput.value.trim() || null,
    };

    try {
      const updated = await api.updateProfile(payload);
      showToast('Profile updated successfully!', 'ok');

      // Refresh sidebar cache
      const updatedUser = await api.me();
      localStorage.setItem('tc_user', JSON.stringify(updatedUser));
      initSharedPageChrome();
      initSidebar('profile');
    } catch (err) {
      showError(profileError, err.message);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = 'Save Profile Changes';
    }
  });

  function showError(el, msg) {
    el.textContent = msg;
    el.classList.remove('hidden');
  }

  await Promise.all([loadSellerCode(), loadProfile()]);
})();
