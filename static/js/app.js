/**
 * Campus Hostel Companion — Client-side JavaScript
 *
 * Responsibilities:
 *   1. Auto-dismiss flash alerts after a timeout.
 *   2. Highlight the active navigation tab.
 *   3. Simple client-side form validation.
 */

/* =========================================================================
   1. Auto-dismiss flash alerts after 5 seconds
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.style.transition = 'opacity 0.4s ease';
      alert.style.opacity = '0';
      setTimeout(function () {
        alert.remove();
      }, 400);
    }, 5000);
  });
});

/* =========================================================================
   2. Active Navigation Tab
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  const currentPath = window.location.pathname;
  document.querySelectorAll('.navbar__tab').forEach(function (link) {
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active');
    }
  });
});

/* =========================================================================
   3. Raise-complaint form validation
   ========================================================================= */
document.addEventListener('DOMContentLoaded', function () {
  const forms = document.querySelectorAll('form');
  forms.forEach(function (form) {
    form.addEventListener('submit', function (e) {
      const requiredInputs = form.querySelectorAll('[required]');
      let hasError = false;

      requiredInputs.forEach(function (input) {
        if (!input.value.trim()) {
          input.style.borderColor = '#111111';
          hasError = true;
        } else {
          input.style.borderColor = '';
        }
      });

      if (hasError) {
        e.preventDefault();
      }
    });
  });
});
