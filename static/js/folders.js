/**
 * folders.js — Vanilla JS for the DocChat folder tree UI.
 *
 * Features:
 *  - Inline folder create (Enter key in .new-folder-input)
 *  - Inline folder rename (double-click or rename button)
 *  - Folder delete via #deleteFolderModal
 *  - HTML5 drag-and-drop for folder reordering
 *  - Document row checkboxes → selection toolbar
 *  - "Move to Folder" modal → bulk AJAX moves
 *  - "Move to Root" bulk action
 *  - Tree collapse/expand state persisted in localStorage
 */

(function () {
  'use strict';

  // ── Utilities ────────────────────────────────────────────────────────────

  function getCsrf() {
    const el = document.getElementById('csrf-token');
    return el ? el.value : '';
  }

  function urlFromTpl(tplId, id) {
    const el = document.getElementById(tplId);
    return el ? el.value.replace('__ID__', id) : '';
  }

  function showToast(message, type = 'info') {
    // Reuse the global showToast defined in main.js if available
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    } else {
      console.warn('[folders.js] toast:', type, message);
    }
  }

  async function postJSON(url, data) {
    const formData = new FormData();
    for (const [k, v] of Object.entries(data)) {
      formData.append(k, v);
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData,
    });
    return res.json();
  }

  // ── localStorage tree state ──────────────────────────────────────────────

  const LS_KEY = 'docchat_folder_tree_open';

  function getOpenSet() {
    try {
      return new Set(JSON.parse(localStorage.getItem(LS_KEY) || '[]'));
    } catch {
      return new Set();
    }
  }

  function saveOpenSet(set) {
    localStorage.setItem(LS_KEY, JSON.stringify([...set]));
  }

  function restoreTreeState() {
    const open = getOpenSet();
    open.forEach(id => {
      const el = document.getElementById(`folder-children-${id}`);
      const toggle = document.getElementById(`toggle-${id}`);
      if (el) {
        el.classList.add('show');
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
      }
    });
  }

  function bindCollapseTracking() {
    document.addEventListener('show.bs.collapse', e => {
      const id = e.target.id.replace('folder-children-', '');
      if (!id) return;
      const open = getOpenSet();
      open.add(id);
      saveOpenSet(open);
    });
    document.addEventListener('hide.bs.collapse', e => {
      const id = e.target.id.replace('folder-children-', '');
      if (!id) return;
      const open = getOpenSet();
      open.delete(id);
      saveOpenSet(open);
    });
  }

  // ── (bindFolderCreate removed: using createFolderModal instead) ──────────

  // ── Inline folder RENAME ─────────────────────────────────────────────────

  function bindFolderRename() {
    // Bind rename buttons in the tree
    document.addEventListener('click', function (e) {
      const btn = e.target.closest('.btn-folder-rename');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      startInlineRename(btn.dataset.folderId, btn.dataset.folderName);
    });

    // Bind the "Rename" button on the folder-detail page header
    const headerRenameBtn = document.getElementById('btn-rename-folder');
    if (headerRenameBtn) {
      headerRenameBtn.addEventListener('click', function () {
        startInlineRename(
          this.dataset.folderId,
          this.dataset.folderName,
          /* isHeader */ true
        );
      });
    }
  }

  function startInlineRename(folderId, currentName, isHeader = false) {
    const renameUrl = urlFromTpl('folder-rename-url-tpl', folderId);

    if (isHeader) {
      // In-place edit on the h1 in folder_detail.html
      const nameEl = document.getElementById('folder-page-name');
      if (!nameEl) return;
      const origTag = nameEl.tagName.toLowerCase();
      const origClass = nameEl.className;
      const input = document.createElement('input');
      input.type = 'text';
      input.value = currentName;
      input.className = 'folder-rename-input form-control form-control-sm d-inline-block w-auto';
      nameEl.replaceWith(input);
      input.focus();
      input.select();

      async function commitRename() {
        const newName = input.value.trim();
        if (!newName || newName === currentName) {
          // Restore original
          const restored = document.createElement(origTag);
          restored.id = 'folder-page-name';
          restored.className = origClass;
          restored.textContent = currentName;
          input.replaceWith(restored);
          return;
        }
        const data = await postJSON(renameUrl, { name: newName });
        if (data.success) {
          const restored = document.createElement(origTag);
          restored.id = 'folder-page-name';
          restored.className = origClass;
          restored.textContent = data.name;
          input.replaceWith(restored);
          document.title = `${data.name} — DocChat`;
          showToast(`Renamed to "${data.name}".`, 'success');
        } else {
          showToast(data.error || 'Rename failed.', 'danger');
          const restored = document.createElement(origTag);
          restored.id = 'folder-page-name';
          restored.className = origClass;
          restored.textContent = currentName;
          input.replaceWith(restored);
        }
      }

      input.addEventListener('blur', commitRename);
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
        if (e.key === 'Escape') { input.blur(); }
      });
    } else {
      // Inline rename in the sidebar tree node label
      const labelEl = document.querySelector(
        `.folder-node[data-folder-id="${folderId}"] .folder-label`
      );
      if (!labelEl) return;
      const input = document.createElement('input');
      input.type = 'text';
      input.value = currentName;
      input.className = 'new-folder-input';
      input.style.cssText = 'max-width:110px; font-size:13.5px;';
      labelEl.replaceWith(input);
      input.focus();
      input.select();

      async function commitTreeRename() {
        const newName = input.value.trim();
        const newLabel = document.createElement('span');
        newLabel.className = 'folder-label';
        if (!newName || newName === currentName) {
          newLabel.textContent = currentName;
          input.replaceWith(newLabel);
          return;
        }
        const data = await postJSON(renameUrl, { name: newName });
        newLabel.textContent = data.success ? data.name : currentName;
        input.replaceWith(newLabel);
        if (data.success) {
          showToast(`Renamed to "${data.name}".`, 'success');
        } else {
          showToast(data.error || 'Rename failed.', 'danger');
        }
      }

      input.addEventListener('blur', commitTreeRename);
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); commitTreeRename(); }
        if (e.key === 'Escape') { input.blur(); }
      });
    }
  }

  // ── Folder DELETE ────────────────────────────────────────────────────────

  function bindFolderDelete() {
    // Populate modal with folder name when triggered from tree or header
    const modal = document.getElementById('deleteFolderModal');
    if (!modal) return;

    modal.addEventListener('show.bs.modal', function (e) {
      const trigger = e.relatedTarget;
      if (!trigger) return;
      const folderId = trigger.dataset.folderId;
      const folderName = trigger.dataset.folderName;
      document.getElementById('deleteFolderName').textContent = folderName;
      const confirmBtn = document.getElementById('confirmDeleteFolderBtn');
      confirmBtn.dataset.folderId = folderId;
      confirmBtn.dataset.folderName = folderName;
    });

    document.getElementById('confirmDeleteFolderBtn').addEventListener('click', async function () {
      const folderId = this.dataset.folderId;
      const folderName = this.dataset.folderName;
      if (!folderId) return;

      const deleteUrl = urlFromTpl('folder-delete-url-tpl', folderId);
      const btnText = document.getElementById('deleteFolderBtnText');
      const btnLoader = document.getElementById('deleteFolderBtnLoader');

      btnText.style.display = 'none';
      btnLoader.style.display = 'flex';
      this.disabled = true;

      try {
        const data = await postJSON(deleteUrl, {});
        if (data.success) {
          showToast(`Folder "${folderName}" deleted.`, 'success');
          // Close modal and reload to update tree
          const bsModal = bootstrap.Modal.getInstance(modal);
          if (bsModal) bsModal.hide();
          window.location.href = '/documents/';
        } else {
          showToast(data.error || 'Delete failed.', 'danger');
        }
      } catch {
        showToast('Network error.', 'danger');
      } finally {
        btnText.style.display = '';
        btnLoader.style.display = 'none';
        this.disabled = false;
      }
    });
  }

  // ── HTML5 Drag-and-Drop (folder reorder) ─────────────────────────────────

  let draggedFolderId = null;

  function bindDragDrop() {
    const tree = document.getElementById('folder-tree-root');
    if (!tree) return;

    // dragstart on folder nodes
    tree.addEventListener('dragstart', function (e) {
      const node = e.target.closest('.folder-node');
      if (!node) return;
      draggedFolderId = node.dataset.folderId;
      e.dataTransfer.effectAllowed = 'move';
      node.style.opacity = '0.5';
    });

    tree.addEventListener('dragend', function (e) {
      const node = e.target.closest('.folder-node');
      if (node) node.style.opacity = '';
      // Remove all highlights
      tree.querySelectorAll('.folder-node').forEach(n => {
        n.classList.remove('drag-over', 'drag-invalid');
      });
      draggedFolderId = null;
    });

    tree.addEventListener('dragover', function (e) {
      e.preventDefault();
      const node = e.target.closest('.folder-node');
      if (!node || node.dataset.folderId === draggedFolderId) return;
      e.dataTransfer.dropEffect = 'move';
      tree.querySelectorAll('.folder-node').forEach(n => n.classList.remove('drag-over', 'drag-invalid'));
      node.classList.add('drag-over');
    });

    tree.addEventListener('dragleave', function (e) {
      const node = e.target.closest('.folder-node');
      if (node) node.classList.remove('drag-over', 'drag-invalid');
    });

    tree.addEventListener('drop', async function (e) {
      e.preventDefault();
      const targetNode = e.target.closest('.folder-node');
      if (!targetNode || !draggedFolderId) return;
      targetNode.classList.remove('drag-over', 'drag-invalid');

      const targetId = targetNode.dataset.folderId;
      if (targetId === draggedFolderId) return;

      const moveUrl = urlFromTpl('folder-move-url-tpl', draggedFolderId);
      const data = await postJSON(moveUrl, { new_parent_id: targetId });
      if (data.success) {
        showToast('Folder moved.', 'success');
        window.location.reload();
      } else {
        showToast(data.error || 'Move failed.', 'danger');
        targetNode.classList.add('drag-invalid');
      }
    });
  }

  // ── Document row checkboxes + selection toolbar ───────────────────────────

  function bindDocCheckboxes() {
    const selectAll = document.getElementById('select-all-docs');
    const toolbar = document.getElementById('selection-toolbar');
    const countEl = document.getElementById('selection-count');
    if (!toolbar) return;

    function getChecked() {
      return [...document.querySelectorAll('.doc-checkbox:checked')];
    }

    function updateToolbar() {
      const checked = getChecked();
      if (countEl) countEl.textContent = checked.length;
      if (checked.length > 0) {
        toolbar.classList.add('active');
      } else {
        toolbar.classList.remove('active');
      }
    }

    document.addEventListener('change', function (e) {
      if (e.target.id === 'select-all-docs') {
        document.querySelectorAll('.doc-checkbox').forEach(cb => {
          cb.checked = e.target.checked;
        });
      }
      updateToolbar();
    });

    // Clear selection button
    const clearBtn = document.getElementById('toolbar-clear-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        document.querySelectorAll('.doc-checkbox').forEach(cb => cb.checked = false);
        if (selectAll) selectAll.checked = false;
        updateToolbar();
      });
    }

    // Bulk delete documents — confirmed via #bulkDeleteDocsModal instead of a native confirm()
    const deleteBtn = document.getElementById('toolbar-delete-btn');
    const bulkDeleteModalEl = document.getElementById('bulkDeleteDocsModal');
    if (deleteBtn && bulkDeleteModalEl && window.bootstrap) {
      const bulkDeleteModal = new bootstrap.Modal(bulkDeleteModalEl);
      const confirmBtn = document.getElementById('confirmBulkDeleteDocsBtn');
      const cancelBtn = document.getElementById('bulkDeleteDocsCancelBtn');
      const closeBtn = document.getElementById('bulkDeleteDocsModalClose');
      const countEl2 = document.getElementById('bulkDeleteDocsCount');
      const btnText = document.getElementById('bulkDeleteDocsBtnText');
      const btnLoader = document.getElementById('bulkDeleteDocsBtnLoader');

      deleteBtn.addEventListener('click', function () {
        const ids = getChecked().map(cb => cb.value);
        if (!ids.length) return;
        countEl2.textContent = ids.length;
        bulkDeleteModal.show();
      });

      confirmBtn.addEventListener('click', async function () {
        const ids = getChecked().map(cb => cb.value);
        if (!ids.length) {
          bulkDeleteModal.hide();
          return;
        }

        confirmBtn.disabled = true;
        cancelBtn.disabled = true;
        closeBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'inline-flex';

        let successCount = 0;
        let failCount = 0;

        for (const id of ids) {
          try {
            const url = `/documents/${id}/delete/`;
            const data = await postJSON(url, {});
            if (data.success) {
              successCount++;
            } else {
              failCount++;
            }
          } catch {
            failCount++;
          }
        }

        bulkDeleteModal.hide();
        confirmBtn.disabled = false;
        cancelBtn.disabled = false;
        closeBtn.disabled = false;
        btnText.style.display = '';
        btnLoader.style.display = 'none';

        if (successCount > 0) {
          showToast(`${successCount} document(s) deleted.`, 'success');
          setTimeout(() => window.location.reload(), 800);
        }
        if (failCount > 0) {
          showToast(`Failed to delete ${failCount} document(s).`, 'danger');
        }
      });
    }
  }

  // ── Move documents modal ──────────────────────────────────────────────────

  function bindMoveDocsModal() {
    const confirmBtn = document.getElementById('confirmMoveDocsBtn');
    if (!confirmBtn) return;

    confirmBtn.addEventListener('click', async function () {
      const selected = document.querySelector('input[name="move_target_folder"]:checked');
      if (!selected) {
        showToast('Please select a destination folder.', 'warning');
        return;
      }
      const folderId = selected.value; // '' = root
      const ids = [...document.querySelectorAll('.doc-checkbox:checked')].map(cb => cb.value);
      if (!ids.length) return;

      const btnText = document.getElementById('moveBtnText');
      const btnLoader = document.getElementById('moveBtnLoader');
      if (btnText) btnText.style.display = 'none';
      if (btnLoader) btnLoader.style.display = 'flex';
      confirmBtn.disabled = true;

      await bulkMoveDocuments(ids, folderId);

      if (btnText) btnText.style.display = '';
      if (btnLoader) btnLoader.style.display = 'none';
      confirmBtn.disabled = false;

      // Close modal
      const modal = document.getElementById('moveFolderModal');
      if (modal) {
        const bsModal = bootstrap.Modal.getInstance(modal);
        if (bsModal) bsModal.hide();
      }
    });
  }

  async function bulkMoveDocuments(docIds, folderId) {
    const moveTpl = document.getElementById('doc-move-url-tpl');
    if (!moveTpl) return;

    let successCount = 0;
    for (const id of docIds) {
      const url = moveTpl.value.replace('__ID__', id);
      try {
        const data = await postJSON(url, { folder_id: folderId });
        if (data.success) {
          successCount++;
          // Update folder badge cell in table
          updateDocFolderCell(id, data.folder_id, data.folder_name);
        }
      } catch {
        // continue
      }
    }

    if (successCount > 0) {
      const dest = folderId ? `folder` : `"All Documents" (root)`;
      showToast(`${successCount} document(s) moved to ${dest}.`, 'success');
      // Uncheck all
      document.querySelectorAll('.doc-checkbox').forEach(cb => cb.checked = false);
      const selectAll = document.getElementById('select-all-docs');
      if (selectAll) selectAll.checked = false;
      const toolbar = document.getElementById('selection-toolbar');
      if (toolbar) toolbar.classList.remove('active');
    }
  }

  function updateDocFolderCell(docId, folderId, folderName) {
    const cell = document.getElementById(`folder-cell-${docId}`);
    if (!cell) return;

    if (folderId && folderName) {
      cell.innerHTML = `
        <a href="/documents/folders/${folderId}/" class="folder-badge" title="${folderName}">
          <i class="bi bi-folder-fill" style="font-size:10px;"></i>
          ${folderName}
        </a>`;
    } else {
      cell.innerHTML = `<span class="no-folder-badge">—</span>`;
    }
  }

  // ── Create folder modal ──────────────────────────────────────────────────

  function bindCreateFolderModal() {
    const modal = document.getElementById('createFolderModal');
    if (!modal) return;

    const input = document.getElementById('modal-new-folder-name');
    const confirmBtn = document.getElementById('confirmCreateFolderBtn');
    const createUrl = document.getElementById('folder-create-url');

    modal.addEventListener('shown.bs.modal', () => {
      input.focus();
    });

    modal.addEventListener('show.bs.modal', e => {
      const trigger = e.relatedTarget;
      if (!input.hasAttribute('data-default-parent')) {
        input.setAttribute('data-default-parent', input.dataset.parentId || '');
      }
      if (trigger && trigger.hasAttribute('data-folder-id')) {
        input.dataset.parentId = trigger.dataset.folderId;
      } else {
        input.dataset.parentId = input.getAttribute('data-default-parent');
      }
    });

    async function doCreate() {
      const name = input.value.trim();
      if (!name) {
        input.focus();
        return;
      }

      const parentId = input.dataset.parentId || '';
      const payload = { name };
      if (parentId) payload.parent_id = parentId;

      const btnText = document.getElementById('createFolderBtnText');
      const btnLoader = document.getElementById('createFolderBtnLoader');

      btnText.style.display = 'none';
      btnLoader.style.display = 'flex';
      confirmBtn.disabled = true;
      input.disabled = true;

      try {
        const data = await postJSON(createUrl.value, payload);
        if (data.success) {
          showToast(`Folder "${data.name}" created.`, 'success');
          window.location.reload();
        } else {
          showToast(data.error || 'Could not create folder.', 'danger');
        }
      } catch {
        showToast('Network error.', 'danger');
      } finally {
        btnText.style.display = '';
        btnLoader.style.display = 'none';
        confirmBtn.disabled = false;
        input.disabled = false;
      }
    }

    confirmBtn.addEventListener('click', doCreate);
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        doCreate();
      }
    });
  }

  // ── Move Single Folder modal ──────────────────────────────────────────────

  function bindMoveSingleFolderModal() {
    const modal = document.getElementById('moveSingleFolderModal');
    if (!modal) return;

    modal.addEventListener('show.bs.modal', function(e) {
      const trigger = e.relatedTarget;
      if (!trigger) return;
      const folderId = trigger.dataset.folderId;
      const folderName = trigger.dataset.folderName;
      document.getElementById('moveSingleFolderName').textContent = folderName;
      document.getElementById('confirmMoveSingleFolderBtn').dataset.folderId = folderId;

      // Hide the folder itself and its children from the picker? Simple: just hide itself.
      // A full check would disable descendant folders too to avoid loops.
      document.querySelectorAll('#single-folder-picker-list .folder-picker-item').forEach(item => {
        const radio = item.querySelector('input[type="radio"]');
        if (radio && radio.value === folderId) {
          item.style.display = 'none';
        } else {
          item.style.display = '';
        }
      });
    });

    const confirmBtn = document.getElementById('confirmMoveSingleFolderBtn');
    if (!confirmBtn) return;
    confirmBtn.addEventListener('click', async function() {
      const folderId = this.dataset.folderId;
      const selected = document.querySelector('input[name="move_single_target_folder"]:checked');
      if (!selected) {
        showToast('Please select a destination.', 'warning');
        return;
      }
      const newParentId = selected.value;
      if (folderId === newParentId) return;

      const btnText = document.getElementById('moveSingleBtnText');
      const btnLoader = document.getElementById('moveSingleBtnLoader');
      btnText.style.display = 'none';
      btnLoader.style.display = 'flex';
      this.disabled = true;

      const moveUrl = urlFromTpl('folder-move-url-tpl', folderId);
      try {
        const data = await postJSON(moveUrl, { new_parent_id: newParentId });
        if (data.success) {
          showToast('Folder moved.', 'success');
          window.location.reload();
        } else {
          showToast(data.error || 'Move failed. Cannot move into itself or a child folder.', 'danger');
        }
      } catch {
        showToast('Network error.', 'danger');
      } finally {
        btnText.style.display = '';
        btnLoader.style.display = 'none';
        this.disabled = false;
      }
    });
  }

  // ── Add Documents to Folder Modal ──────────────────────────────────────────
  
  function bindAddDocsModal() {
    const modal = document.getElementById('addDocsModal');
    if (!modal) return;

    modal.addEventListener('show.bs.modal', function(e) {
      const trigger = e.relatedTarget;
      if (!trigger) return;
      
      const folderId = trigger.dataset.folderId;
      const folderName = trigger.dataset.folderName;
      
      const nameEl = document.getElementById('addDocsFolderName');
      if (nameEl) nameEl.textContent = folderName;
      
      const confirmBtn = document.getElementById('confirmAddDocsBtn');
      if (confirmBtn) confirmBtn.dataset.folderId = folderId;

      // Uncheck all checkboxes on open
      document.querySelectorAll('.add-doc-checkbox').forEach(cb => cb.checked = false);
    });

    const confirmBtn = document.getElementById('confirmAddDocsBtn');
    if (!confirmBtn) return;
    
    confirmBtn.addEventListener('click', async function() {
      const folderId = this.dataset.folderId;
      const selectedIds = [...document.querySelectorAll('.add-doc-checkbox:checked')].map(cb => cb.value);
      
      if (!selectedIds.length) {
        showToast('Please select at least one document.', 'warning');
        return;
      }

      const btnText = document.getElementById('addDocsBtnText');
      const btnLoader = document.getElementById('addDocsBtnLoader');
      btnText.style.display = 'none';
      btnLoader.style.display = 'flex';
      this.disabled = true;

      await bulkMoveDocuments(selectedIds, folderId);

      btnText.style.display = '';
      btnLoader.style.display = 'none';
      this.disabled = false;

      const bsModal = bootstrap.Modal.getInstance(modal);
      if (bsModal) bsModal.hide();
      
      // Optionally reload to update counts or show toast
      showToast(`${selectedIds.length} document(s) added to the folder.`, 'success');
      setTimeout(() => window.location.reload(), 800);
    });
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    restoreTreeState();
    bindCollapseTracking();
    bindFolderRename();
    bindFolderDelete();
    bindDragDrop();
    bindDocCheckboxes();
    bindMoveDocsModal();
    bindCreateFolderModal();
    bindMoveSingleFolderModal();
    bindAddDocsModal();
  });

})();
