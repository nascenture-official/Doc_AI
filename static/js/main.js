/* ==============================================================
   DocChat — main.js
   UI interactions: sidebar toggle, avatar preview, toasts, etc.
   ============================================================== */

$(function () {

  /* ── Sidebar toggle (mobile) ─────────────────────────────── */
  $('#sidebar-toggle').on('click', function () {
    $('#sidebar').toggleClass('open');
    $('#sidebar-overlay').toggleClass('d-none');
  });

  $('#sidebar-overlay').on('click', function () {
    $('#sidebar').removeClass('open');
    $(this).addClass('d-none');
  });

  /* ── Auto-dismiss alerts after 5 s ──────────────────────── */
  setTimeout(function () {
    $('.alert-dismissible').fadeOut(600, function () {
      $(this).remove();
    });
  }, 5000);

  /* ── Avatar image preview on file select ────────────────── */
  $('#id_avatar').on('change', function () {
    const file = this.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      showToast('Please select a valid image file.', 'danger');
      this.value = '';
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      showToast('Image must be smaller than 5 MB.', 'danger');
      this.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = function (e) {
      $('#avatar-preview').attr('src', e.target.result).removeClass('d-none');
      $('.avatar-initials-lg').addClass('d-none');
      $('#btn-remove-avatar').removeClass('d-none');
      // If there is an allauth/django clear checkbox, uncheck it since we are uploading a new one
      $('#avatar-clear_id').prop('checked', false);
    };
    reader.readAsDataURL(file);
  });

  /* ── Click-overlay to trigger file input ────────────────── */
  $('#avatar-overlay-btn').on('click', function () {
    $('#id_avatar').trigger('click');
  });

  /* ── Remove avatar click handler ────────────────────────── */
  $('#btn-remove-avatar').on('click', function () {
    $('#id_avatar').val('');
    $('#avatar-preview').addClass('d-none').attr('src', '');
    $('.avatar-initials-lg').removeClass('d-none');
    $(this).addClass('d-none');
    // Check the Django clear checkbox to tell backend to delete avatar
    $('#avatar-clear_id').prop('checked', true);
  });

  /* ── Password strength indicator ────────────────────────── */
  $('#id_password1').on('input', function () {
    const val = $(this).val();
    const $bar = $('#strength-bar');
    const $label = $('#strength-label');
    if (!$bar.length) return;

    let score = 0;
    if (val.length >= 8) score++;
    if (/[A-Z]/.test(val)) score++;
    if (/[0-9]/.test(val)) score++;
    if (/[^A-Za-z0-9]/.test(val)) score++;

    const levels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
    const colors = ['', '#ef4444', '#f59e0b', '#22c55e', '#6366f1'];
    const widths = ['0%', '25%', '50%', '75%', '100%'];

    $bar.css({ width: widths[score], background: colors[score] });
    $label.text(levels[score] || '').css('color', colors[score]);
  });

  /* ── Form submission loading state ──────────────────────── */
  $('form').on('submit', function () {
    const $btn = $(this).find('[type="submit"]');
    $btn.prop('disabled', true).html(
      '<span class="spinner-border spinner-border-sm me-2" role="status"></span> Please wait…'
    );
  });

  /* ── Toast helper ───────────────────────────────────────── */
  function showToast(message, type = 'info') {
    const id = 'toast-' + Date.now();
    const icons = { success: '✅', danger: '❌', info: 'ℹ️', warning: '⚠️' };
    const $toast = $(`
      <div id="${id}" class="alert alert-${type} alert-dismissible d-flex align-items-center gap-2 mb-2"
           style="position:fixed;bottom:24px;right:24px;z-index:9999;min-width:280px;max-width:380px;" role="alert">
        <span>${icons[type] || ''}</span>
        <span>${message}</span>
        <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="alert"></button>
      </div>
    `);
    $('body').append($toast);
    setTimeout(() => $toast.fadeOut(400, () => $toast.remove()), 4000);
  }

  /* expose globally */
  window.showToast = showToast;

});
