/**
 * Campus Hostel Companion — Client-side JavaScript
 *
 * Responsibilities:
 *   1. Show/hide Login and Sign-up modals on the landing page.
 *   2. Auto-dismiss flash messages after a timeout.
 *   3. Mark the active nav link.
 *   4. (Future) Form validation before submission.
 *
 * No external libraries — vanilla JS only.
 */

/* =========================================================================
   1. Modal helpers (Login / Sign-up)
   ========================================================================= */

/**
 * Open a modal by its ID.
 * @param {string} modalId - The id of the modal overlay element.
 */
function openModal(modalId) {
  const overlay = document.getElementById(modalId);
  if (overlay) {
    overlay.classList.add('active');
    // Focus the first input for accessibility
    const firstInput = overlay.querySelector('input');
    if (firstInput) setTimeout(() => firstInput.focus(), 80);
  }
}

/**
 * Close a modal by its ID.
 * @param {string} modalId - The id of the modal overlay element.
 */
function closeModal(modalId) {
  const overlay = document.getElementById(modalId);
  if (overlay) overlay.classList.remove('active');
}

// Close modal when clicking the dark overlay background
document.addEventListener('click', function (e) {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});

// Close modal on Escape key
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(function (m) {
      m.classList.remove('active');
    });
  }
});


/* =========================================================================
   2. Auto-open modals if Flask signals it (via data attributes)
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  // Flask can set data-open-modal on <body> to auto-open a modal on page load
  // e.g., <body data-open-modal="loginModal">
  const body = document.body;
  const autoOpen = body.dataset.openModal;
  if (autoOpen) {
    openModal(autoOpen);
  }
});


/* =========================================================================
   3. Auto-dismiss flash alerts after 5 seconds
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = 'opacity 0.5s ease';
      alert.style.opacity = '0';
      setTimeout(function () { alert.remove(); }, 500);
    }, 5000);
  });
});


/* =========================================================================
   4. Highlight the active navigation link
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  const currentPath = window.location.pathname;
  document.querySelectorAll('.navbar__links a').forEach(function (link) {
    // Match exact path or treat /dashboard as home for the nav
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active');
    }
  });
});


/* =========================================================================
   5. Raise-complaint form: simple client-side validation
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  const complaintForm = document.getElementById('complaintForm');
  if (!complaintForm) return;

  complaintForm.addEventListener('submit', function (e) {
    const title    = document.getElementById('title');
    const category = document.getElementById('category');
    const desc     = document.getElementById('description');
    let valid = true;

    [title, category, desc].forEach(function (field) {
      if (!field) return;
      if (!field.value.trim()) {
        field.style.borderColor = '#e74c3c';
        valid = false;
      } else {
        field.style.borderColor = '';
      }
    });

    if (!valid) {
      e.preventDefault();
      // Scroll to the first invalid field
      const firstInvalid = complaintForm.querySelector('[style*="e74c3c"]');
      if (firstInvalid) firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  });
});
