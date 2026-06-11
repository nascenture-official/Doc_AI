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
function setAvatarClearCheckbox(checked) {
      const $clearCheckbox = $('#avatar-clear_id, #id_avatar-clear_id, input[name="avatar-clear"]');
      if ($clearCheckbox.length) {
        $clearCheckbox.prop('checked', checked);
      }
    }

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
        setAvatarClearCheckbox(false);
      };
      reader.readAsDataURL(file);
    });

  /* ── Click-overlay to trigger file input ────────────────── */
  $('#avatar-overlay-btn').on('click', function () {
    $('#id_avatar').trigger('click');
  });

  /* ── CSRF cookie helper ──────────────────────────────────── */
  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  /* ── Remove avatar click handler (AJAX) ─────────────────── */
  $('#btn-remove-avatar').on('click', function () {
    const $btn = $(this);
    const url = $btn.data('url');
    const csrfToken = getCookie('csrftoken') || $('[name=csrfmiddlewaretoken]').val();

    setAvatarClearCheckbox(true);

    // Loading state
    $btn.prop('disabled', true).html(
      '<span class="spinner-border spinner-border-sm me-1" role="status"></span> Removing…'
    );

    fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest',
      },
    })
      .then(function (res) {
        if (!res.ok) {
          throw new Error('Server returned ' + res.status);
        }
        return res.json();
      })
      .then(function (data) {
        if (data.success) {
          $('#id_avatar').val('');
          setAvatarClearCheckbox(true);
          $('#avatar-preview').addClass('d-none').attr('src', '');
          $('.avatar-initials-lg').removeClass('d-none');
          $btn.addClass('d-none');
          showToast('Avatar removed successfully.', 'success');
        } else {
          setAvatarClearCheckbox(false);
          showToast(data.error || 'Could not remove avatar.', 'danger');
          $btn.prop('disabled', false).html('<i class="bi bi-trash-fill me-1"></i> Remove Avatar');
        }
      })
      .catch(function (err) {
        console.error('Remove avatar error:', err);
        setAvatarClearCheckbox(false);
        showToast('Something went wrong. Please try again.', 'danger');
        $btn.prop('disabled', false).html('<i class="bi bi-trash-fill me-1"></i> Remove Avatar');
      });
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
  $('form:not(#chat-form)').on('submit', function () {
    const $btn = $(this).find('[type="submit"]');
    $btn.prop('disabled', true).html(
      '<span class="spinner-border spinner-border-sm me-2" role="status"></span> Please wait…'
    );
  });

  /* ── Toast helper ───────────────────────────────────────── */
  function showToast(message, type = 'info') {
    let $container = $('#toast-container');
    if (!$container.length) {
      $container = $('<div id="toast-container"></div>').appendTo('body');
    }

    const id = 'toast-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
    const icons = {
      success: '<i class="bi bi-check-circle-fill"></i>',
      danger: '<i class="bi bi-x-circle-fill"></i>',
      info: '<i class="bi bi-info-circle-fill"></i>',
      warning: '<i class="bi bi-exclamation-triangle-fill"></i>'
    };

    const $toast = $(`
      <div id="${id}" class="custom-toast toast-${type}" role="alert">
        <div class="toast-icon">${icons[type] || icons.info}</div>
        <div class="toast-content">${message}</div>
        <button type="button" class="toast-close" aria-label="Close">
          <i class="bi bi-x"></i>
        </button>
      </div>
    `);

    $container.append($toast);

    // Auto-remove after 4 seconds
    const timeoutId = setTimeout(() => {
      dismissToast($toast);
    }, 4000);

    // Close button handler
    $toast.find('.toast-close').on('click', function () {
      clearTimeout(timeoutId);
      dismissToast($toast);
    });
  }

  function dismissToast($toast) {
    $toast.addClass('fade-out');
    setTimeout(() => {
      $toast.remove();
      const $container = $('#toast-container');
      if ($container.length && $container.children().length === 0) {
        $container.remove();
      }
    }, 300);
  }

  /* ── Theme toggle ────────────────────────────────────────── */
  const $themeToggle = $('#theme-toggle');
  const $themeIcon = $('#theme-icon');

  function updateThemeIcon(theme) {
    if (theme === 'light') {
      $themeIcon.removeClass('bi-moon').addClass('bi-sun');
    } else {
      $themeIcon.removeClass('bi-sun').addClass('bi-moon');
    }
  }

  // Set initial icon state on page load
  const initialTheme = document.documentElement.getAttribute('data-theme') || 'dark';
  updateThemeIcon(initialTheme);

  $themeToggle.on('click', function () {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
  });

  /* expose globally */
  window.showToast = showToast;

});
