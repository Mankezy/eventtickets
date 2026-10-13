// Umumiy JS: forma yuborilganda yuklanish ko'rsatkichi
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-loading]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.tagName === 'BUTTON' && btn.type === 'submit') {
        setTimeout(function () {
          btn.disabled = true;
          btn.insertAdjacentHTML('afterbegin', '<span class="spinner-border spinner-border-sm me-2"></span>');
        }, 0);
      }
    });
  });
});
