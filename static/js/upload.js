/* ==============================================================
   DocChat — upload.js
   Handles drag-and-drop, multiple uploads, progress tracking,
   and document actions.
   ============================================================== */

$(function () {
  const $dropZone = $('#drop-zone');
  const $fileInput = $('#file-input');
  const $uploadQueue = $('#upload-queue');
  const $queueSection = $('#queue-section');
  const $emptyState = $('#empty-state');
  const $tableSection = $('#table-section');
  const $tbody = $('#documents-tbody');
  const $docCounter = $('#doc-counter');

  const uploadUrl = $('#upload-url').val();
  const csrfToken = $('#csrf-token').val() || getCookie('csrftoken');

  const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  function formatBytes(bytes, decimals = 1) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }

  // ── Drag & Drop Event Listeners ──────────────────────────
  $dropZone.on('dragenter dragover', function (e) {
    e.preventDefault();
    e.stopPropagation();
    $dropZone.addClass('dragover');
  });

  $dropZone.on('dragleave drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    $dropZone.removeClass('dragover');
  });

  $dropZone.on('drop', function (e) {
    const files = e.originalEvent.dataTransfer.files;
    handleFiles(files);
  });

  $dropZone.on('click', function () {
    $fileInput.trigger('click');
  });

  $fileInput.on('change', function () {
    handleFiles(this.files);
    this.value = ''; // Reset file input so same file can be selected again
  });

  // ── File Upload Logic ────────────────────────────────────
  function handleFiles(files) {
    if (files.length === 0) return;

    // Show queue section
    $queueSection.removeClass('d-none');

    // Limit to maximum of 10 files at once
    const filesToUpload = Array.from(files).slice(0, 10);
    if (files.length > 10) {
      window.showToast('You can only upload up to 10 files at once. The first 10 files will be processed.', 'warning');
    }

    filesToUpload.forEach((file, index) => {
      // Client-side validations
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        window.showToast(`"${file.name}" is not a PDF file. Only PDF files are allowed.`, 'danger');
        return;
      }

      if (file.size > MAX_FILE_SIZE) {
        window.showToast(`"${file.name}" is too large. Max size is 20MB.`, 'danger');
        return;
      }

      uploadFile(file);
    });
  }

  function uploadFile(file) {
    const itemId = 'queue-item-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
    const formattedSize = formatBytes(file.size);

    // Create Queue Item DOM
    const queueItemHTML = `
      <div class="queue-item" id="${itemId}">
        <div class="queue-item-header">
          <div class="queue-file-info">
            <i class="bi bi-file-earmark-pdf-fill queue-file-icon"></i>
            <div>
              <div class="queue-file-name" title="${file.name}">${file.name}</div>
              <div class="queue-file-size">${formattedSize}</div>
            </div>
          </div>
          <span class="badge-status uploading" id="badge-${itemId}">
            <i class="bi bi-cloud-arrow-up-fill me-1"></i> Uploading (0%)
          </span>
        </div>
        <div class="progress-custom">
          <div class="progress-bar-custom" id="bar-${itemId}"></div>
        </div>
      </div>
    `;

    $uploadQueue.append(queueItemHTML);

    // XHR Request to handle upload and monitor progress
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('file', file);

    xhr.open('POST', uploadUrl, true);
    xhr.setRequestHeader('X-CSRFToken', csrfToken);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

    // Monitor Upload Progress
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        $(`#bar-${itemId}`).css('width', percent + '%');
        $(`#badge-${itemId}`)
          .removeClass('ready failed processing')
          .addClass('uploading')
          .html(`<i class="bi bi-cloud-arrow-up-fill me-1"></i> Uploading (${percent}%)`);
      }
    };

    // Upload Complete, Server is processing
    xhr.upload.onload = function () {
      $(`#badge-${itemId}`)
        .removeClass('uploading ready failed')
        .addClass('processing')
        .html(`<span class="spinner-border spinner-border-sm spinner-xs me-1"></span> Processing...`);
      $(`#bar-${itemId}`).css('width', '100%');
    };

    // Response Received
    xhr.onload = function () {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch (err) {
        data = { success: false, error: 'Could not parse server response.' };
      }

      if (xhr.status === 200 && data.success) {
        // Success
        $(`#badge-${itemId}`)
          .removeClass('processing uploading failed')
          .addClass('ready')
          .html(`<i class="bi bi-check-circle-fill"></i> Uploaded`);

        // Add to Table
        addDocumentToTable(data);
        window.showToast(`"${file.name}" uploaded successfully!`, 'success');

        // Automatically hide queue item after 3 seconds
        setTimeout(function () {
          $(`#${itemId}`).fadeOut(300, function () {
            $(this).remove();
            if ($uploadQueue.children().length === 0) {
              $queueSection.addClass('d-none');
            }
          });
        }, 3000);

      } else {
        // Failed
        const errMsg = data.error || 'Upload failed.';
        $(`#badge-${itemId}`)
          .removeClass('processing uploading ready')
          .addClass('failed')
          .html(`<i class="bi bi-exclamation-circle-fill"></i> Failed`);

        $(`#${itemId}`).append(`
          <div style="font-size:12px;color:var(--danger);margin-top:4px;">
            <i class="bi bi-info-circle me-1"></i> ${errMsg}
          </div>
        `);
        window.showToast(`"${file.name}" upload failed: ${errMsg}`, 'danger');
      }
    };

    // Request Error
    xhr.onerror = function () {
      $(`#badge-${itemId}`)
        .removeClass('processing uploading ready')
        .addClass('failed')
        .html(`<i class="bi bi-exclamation-circle-fill"></i> Failed`);
      window.showToast('Network error during upload.', 'danger');
    };

    xhr.send(formData);
  }

  function addDocumentToTable(doc) {
    // Hide empty state if visible
    $emptyState.addClass('d-none');
    $tableSection.removeClass('d-none');

    // Create Row DOM
    const rowHTML = `
      <tr id="doc-row-${doc.id}" style="display:none;">
        <td>
          <input type="checkbox" class="doc-checkbox" value="${doc.id}" id="check-doc-${doc.id}">
        </td>
        <td>
          <div class="doc-title-cell" id="doc-title-cell-${doc.id}">
            <i class="bi bi-file-earmark-pdf-fill text-danger fs-5"></i>
            <span title="${doc.title}" class="text-muted">${doc.title}</span>
          </div>
        </td>
        <td class="d-none d-md-table-cell" id="folder-cell-${doc.id}">
          <span class="no-folder-badge">—</span>
        </td>
        <td class="d-none d-md-table-cell">${doc.uploaded_at}</td>
        <td class="d-none d-sm-table-cell">${formatBytes(doc.file_size)}</td>
        <td id="status-cell-${doc.id}">
          <span class="badge-status processing" 
                id="status-badge-${doc.id}"
                hx-get="/documents/${doc.id}/status/" 
                hx-trigger="every 3s" 
                hx-swap="outerHTML">
            <span class="spinner-border spinner-border-sm spinner-xs me-1"></span> Processing...
          </span>
        </td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <a href="/documents/${doc.id}/download/" class="action-btn" title="Download PDF">
              <i class="bi bi-download"></i>
            </a>
            <button type="button" class="action-btn btn-delete btn-delete-doc" 
                    data-id="${doc.id}" 
                    data-url="/documents/${doc.id}/delete/"
                    data-title="${doc.title}"
                    data-bs-toggle="modal"
                    data-bs-target="#deleteDocModal"
                    title="Delete Document">
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </td>
      </tr>
    `;

    const $row = $(rowHTML);
    $tbody.prepend($row);
    $row.fadeIn(400);

    // Initialize HTMX processing on the new elements
    if (window.htmx) {
      window.htmx.process($row[0]);
    }

    // Update Counter
    updateCounter(1);
  }

  function updateCounter(change) {
    const currentCount = parseInt($docCounter.text()) || 0;
    const newCount = Math.max(0, currentCount + change);
    $docCounter.text(newCount + ' total');
  }

  // ── Document Deletion (Bootstrap Modal) ──────────────────
  const deleteDocModal = document.getElementById('deleteDocModal');
  if (deleteDocModal) {
    deleteDocModal.addEventListener('show.bs.modal', function (event) {
      const button = event.relatedTarget;
      const docId = button.getAttribute('data-id');
      const deleteUrl = button.getAttribute('data-url');
      const docTitle = button.getAttribute('data-title');

      document.getElementById('deleteModalDocTitle').textContent = docTitle;

      const $confirmBtn = $('#confirmDeleteDocBtn');
      
      // Clear previous click listener and bind new one
      $confirmBtn.off('click').on('click', function () {
        $confirmBtn.prop('disabled', true);
        $('#deleteDocBtnText').hide();
        $('#deleteDocBtnLoader').css('display', 'inline-flex');
        $('#deleteDocCancelBtn').prop('disabled', true);
        $('#deleteDocModalClose').prop('disabled', true);

        fetch(deleteUrl, {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest',
          },
        })
        .then(res => {
          if (!res.ok) throw new Error('Server returned ' + res.status);
          return res.json();
        })
        .then(data => {
          const modalInstance = bootstrap.Modal.getInstance(deleteDocModal);
          if (modalInstance) modalInstance.hide();

          if (data.success) {
            $(`#doc-row-${docId}`).fadeOut(300, function () {
              $(this).remove();
              updateCounter(-1);

              // If no rows left, show empty state
              if ($tbody.children('tr').length === 0) {
                $tableSection.addClass('d-none');
                $emptyState.removeClass('d-none');
              }
            });
            window.showToast('Document deleted successfully.', 'success');
          } else {
            window.showToast(data.error || 'Failed to delete document.', 'danger');
          }
        })
        .catch(err => {
          console.error('Delete error:', err);
          window.showToast('Something went wrong. Please try again.', 'danger');
          const modalInstance = bootstrap.Modal.getInstance(deleteDocModal);
          if (modalInstance) modalInstance.hide();
        })
        .finally(() => {
          // Reset modal button states
          $confirmBtn.prop('disabled', false);
          $('#deleteDocBtnText').show();
          $('#deleteDocBtnLoader').hide();
          $('#deleteDocCancelBtn').prop('disabled', false);
          $('#deleteDocModalClose').prop('disabled', false);
        });
      });
    });
  }
});
