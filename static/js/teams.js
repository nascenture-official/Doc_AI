/**
 * teams.js — Vanilla JS for workspace + document sharing UI.
 *
 * Features:
 *  - Create workspace modal (teams:create)
 *  - Invite member modal (teams:invite)
 *  - Member role change / remove (teams:change_role / teams:remove_member)
 *  - Revoke pending invitation (teams:revoke_invite)
 *  - Document share modal: list/add/change-permission/remove (teams:document_shares / document_share_detail)
 */
(function () {
  'use strict';

  function getCsrf() {
    const el = document.getElementById('csrf-token');
    return el ? el.value : '';
  }

  function showToast(message, type = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(message, type);
    } else {
      console.warn('[teams.js] toast:', type, message);
    }
  }

  async function postJSON(url, data) {
    const formData = new FormData();
    for (const [k, v] of Object.entries(data || {})) {
      formData.append(k, v);
    }
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData,
    });
    return res.json();
  }

  async function deleteJSON(url) {
    const res = await fetch(url, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrf() },
    });
    return res.json();
  }

  function setLoading(btn, textId, loaderId, isLoading) {
    document.getElementById(textId).style.display = isLoading ? 'none' : '';
    const loader = document.getElementById(loaderId);
    loader.style.display = isLoading ? 'inline-flex' : 'none';
    btn.disabled = isLoading;
  }

  // ── Create Workspace ─────────────────────────────────────────────────────
  const createWorkspaceBtn = document.getElementById('confirmCreateWorkspaceBtn');
  if (createWorkspaceBtn) {
    createWorkspaceBtn.addEventListener('click', async function () {
      const nameInput = document.getElementById('modal-new-workspace-name');
      const name = nameInput.value.trim();
      if (!name) {
        showToast('Workspace name is required.', 'warning');
        return;
      }
      setLoading(createWorkspaceBtn, 'createWorkspaceBtnText', 'createWorkspaceBtnLoader', true);
      try {
        const data = await postJSON('/teams/create/', { name });
        if (data.success) {
          showToast(`Workspace "${data.name}" created.`, 'success');
          window.location.href = data.url;
        } else {
          showToast(data.error || 'Could not create workspace.', 'danger');
        }
      } catch {
        showToast('Network error.', 'danger');
      } finally {
        setLoading(createWorkspaceBtn, 'createWorkspaceBtnText', 'createWorkspaceBtnLoader', false);
      }
    });
  }

  // ── Invite Member ────────────────────────────────────────────────────────
  const inviteBtn = document.getElementById('confirmInviteMemberBtn');
  if (inviteBtn) {
    inviteBtn.addEventListener('click', async function () {
      const email = document.getElementById('modal-invite-email').value.trim();
      const role = document.getElementById('modal-invite-role').value;
      const workspaceId = inviteBtn.dataset.workspaceId;
      if (!email) {
        showToast('Email is required.', 'warning');
        return;
      }
      setLoading(inviteBtn, 'inviteMemberBtnText', 'inviteMemberBtnLoader', true);
      try {
        const data = await postJSON(`/teams/${workspaceId}/invite/`, { email, role });
        if (data.success) {
          showToast(`Invitation sent to ${data.invitation.email}.`, 'success');
          window.location.reload();
        } else {
          showToast(data.error || 'Could not send invitation.', 'danger');
        }
      } catch {
        showToast('Network error.', 'danger');
      } finally {
        setLoading(inviteBtn, 'inviteMemberBtnText', 'inviteMemberBtnLoader', false);
      }
    });
  }

  // ── Change Member Role ───────────────────────────────────────────────────
  document.querySelectorAll('.member-role-option').forEach(function (option) {
    option.addEventListener('click', async function (e) {
      e.preventDefault();
      const workspaceId = option.dataset.workspaceId;
      const userId = option.dataset.userId;
      const newRole = option.dataset.role;
      const dropdown = option.closest('.dropdown');
      const toggleBtn = dropdown.querySelector('.dropdown-toggle .role-text');
      const toggleBtnEl = dropdown.querySelector('.dropdown-toggle');
      
      toggleBtnEl.disabled = true;
      const originalText = toggleBtn.innerText;
      toggleBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

      const data = await postJSON(`/teams/${workspaceId}/members/${userId}/role/`, { role: newRole });
      if (data.success) {
        showToast(`Role updated to ${data.role}.`, 'success');
        // Update button text and active state
        toggleBtn.innerText = newRole.charAt(0).toUpperCase() + newRole.slice(1);
        dropdown.querySelectorAll('.dropdown-item').forEach(el => el.classList.remove('active'));
        option.classList.add('active');
        toggleBtnEl.disabled = false;
      } else {
        showToast(data.error || 'Could not update role.', 'danger');
        window.location.reload();
      }
    });
  });

  // ── Remove Member ────────────────────────────────────────────────────────
  let memberToRemove = null;
  document.querySelectorAll('.remove-member-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      memberToRemove = {
        workspaceId: btn.dataset.workspaceId,
        userId: btn.dataset.userId,
        row: btn.closest('tr')
      };
      const modalEl = document.getElementById('removeMemberModal');
      if (modalEl) {
        new bootstrap.Modal(modalEl).show();
      } else {
        if (confirm('Remove this member from the workspace?')) {
          executeRemoveMember();
        }
      }
    });
  });

  const confirmRemoveBtn = document.getElementById('confirmRemoveMemberBtn');
  if (confirmRemoveBtn) {
    confirmRemoveBtn.addEventListener('click', executeRemoveMember);
  }

  async function executeRemoveMember() {
    if (!memberToRemove) return;
    const { workspaceId, userId, row } = memberToRemove;
    const data = await postJSON(`/teams/${workspaceId}/members/${userId}/remove/`, {});
    if (data.success) {
      showToast('Member removed.', 'success');
      if (row) row.remove();
    } else {
      showToast(data.error || 'Could not remove member.', 'danger');
    }
    const modalEl = document.getElementById('removeMemberModal');
    if (modalEl) {
      const modalInstance = bootstrap.Modal.getInstance(modalEl);
      if (modalInstance) modalInstance.hide();
    }
  }

  // ── Revoke Invitation ────────────────────────────────────────────────────
  let inviteToRevoke = null;
  document.querySelectorAll('.revoke-invite-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      inviteToRevoke = {
        invitationId: btn.dataset.invitationId,
        row: btn.closest('tr')
      };
      const modalEl = document.getElementById('revokeInviteModal');
      if (modalEl) {
        new bootstrap.Modal(modalEl).show();
      } else {
        if (confirm('Revoke this invitation?')) {
          executeRevokeInvite();
        }
      }
    });
  });

  const confirmRevokeBtn = document.getElementById('confirmRevokeInviteBtn');
  if (confirmRevokeBtn) {
    confirmRevokeBtn.addEventListener('click', executeRevokeInvite);
  }

  async function executeRevokeInvite() {
    if (!inviteToRevoke) return;
    const { invitationId, row } = inviteToRevoke;
    const data = await postJSON(`/teams/invitations/${invitationId}/revoke/`, {});
    if (data.success) {
      showToast('Invitation revoked.', 'success');
      if (row) row.remove();
    } else {
      showToast(data.error || 'Could not revoke invitation.', 'danger');
    }
    const modalEl = document.getElementById('revokeInviteModal');
    if (modalEl) {
      const modalInstance = bootstrap.Modal.getInstance(modalEl);
      if (modalInstance) modalInstance.hide();
    }
  }

  // ── Document Share Modal ─────────────────────────────────────────────────
  const shareModalEl = document.getElementById('documentShareModal');
  if (shareModalEl) {
    let currentDocId = null;

    function renderShares(shares) {
      const list = document.getElementById('documentShareList');
      if (!shares.length) {
        list.innerHTML = '<p style="font-size:13px;color:var(--text-muted);">Not shared with anyone yet.</p>';
        return;
      }
      list.innerHTML = shares.map(function (s) {
        return `
          <div class="d-flex align-items-center justify-content-between" style="padding:8px 0; border-bottom:1px solid var(--border);" data-share-id="${s.id}">
            <div>
              <div style="font-size:13.5px;color:var(--text-primary);">${s.name}</div>
              <div style="font-size:12px;color:var(--text-muted);">${s.email}</div>
            </div>
            <div class="d-flex align-items-center gap-2">
              <div class="dropdown">
                <button class="btn btn-outline-custom btn-sm dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false" style="padding-top: 4px; padding-bottom: 4px; font-weight: 500; min-width: 105px; text-align: left; display: flex; justify-content: space-between; align-items: center;">
                  <span class="permission-text">${s.permission === 'view' ? 'Can View' : 'Can Edit'}</span>
                </button>
                <ul class="dropdown-menu shadow-sm" style="min-width: 120px;">
                  <li><a class="dropdown-item share-permission-option ${s.permission === 'view' ? 'active' : ''}" href="#" data-permission="view">Can View</a></li>
                  <li><a class="dropdown-item share-permission-option ${s.permission === 'edit' ? 'active' : ''}" href="#" data-permission="edit">Can Edit</a></li>
                </ul>
              </div>
              <button type="button" class="btn btn-outline-custom-danger btn-sm remove-share-btn"><i class="bi bi-x"></i></button>
            </div>
          </div>`;
      }).join('');

      list.querySelectorAll('.share-permission-option').forEach(function (option) {
        option.addEventListener('click', async function (e) {
          e.preventDefault();
          const shareId = option.closest('[data-share-id]').dataset.shareId;
          const permission = option.dataset.permission;
          const dropdown = option.closest('.dropdown');
          const toggleBtn = dropdown.querySelector('.dropdown-toggle .permission-text');
          const toggleBtnEl = dropdown.querySelector('.dropdown-toggle');
          
          toggleBtnEl.disabled = true;
          toggleBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

          const data = await postJSON(`/teams/documents/${currentDocId}/shares/${shareId}/`, { permission: permission });
          if (data.success) {
            showToast('Permission updated.', 'success');
            toggleBtn.innerText = permission === 'view' ? 'Can View' : 'Can Edit';
            dropdown.querySelectorAll('.dropdown-item').forEach(el => el.classList.remove('active'));
            option.classList.add('active');
            toggleBtnEl.disabled = false;
          } else {
            showToast(data.error || 'Could not update permission.', 'danger');
            toggleBtnEl.disabled = false;
          }
        });
      });
      list.querySelectorAll('.remove-share-btn').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          const row = btn.closest('[data-share-id]');
          const shareId = row.dataset.shareId;
          const data = await deleteJSON(`/teams/documents/${currentDocId}/shares/${shareId}/`);
          if (data.success) {
            row.remove();
            showToast('Share removed.', 'success');
          } else {
            showToast(data.error || 'Could not remove share.', 'danger');
          }
        });
      });
    }

    shareModalEl.addEventListener('show.bs.modal', async function (evt) {
      const trigger = evt.relatedTarget;
      currentDocId = trigger ? trigger.dataset.docId : shareModalEl.dataset.docId;
      document.getElementById('documentShareList').innerHTML = '<p style="font-size:13px;color:var(--text-muted);">Loading…</p>';
      try {
        const res = await fetch(`/teams/documents/${currentDocId}/shares/`);
        const data = await res.json();
        if (data.success) {
          renderShares(data.shares);
        } else {
          showToast(data.error || 'Could not load sharing info.', 'danger');
        }
      } catch {
        showToast('Network error.', 'danger');
      }
    });

    const addShareBtn = document.getElementById('confirmAddShareBtn');
    if (addShareBtn) {
      addShareBtn.addEventListener('click', async function () {
        const email = document.getElementById('modal-share-email').value.trim();
        const permission = document.getElementById('modal-share-permission').value;
        if (!email) {
          showToast('Email is required.', 'warning');
          return;
        }
        setLoading(addShareBtn, 'addShareBtnText', 'addShareBtnLoader', true);
        try {
          const data = await postJSON(`/teams/documents/${currentDocId}/shares/`, { email, permission });
          if (data.success) {
            showToast(`Shared with ${data.share.email}.`, 'success');
            document.getElementById('modal-share-email').value = '';
            const res = await fetch(`/teams/documents/${currentDocId}/shares/`);
            const listData = await res.json();
            if (listData.success) renderShares(listData.shares);
          } else {
            showToast(data.error || 'Could not share document.', 'danger');
          }
        } catch {
          showToast('Network error.', 'danger');
        } finally {
          setLoading(addShareBtn, 'addShareBtnText', 'addShareBtnLoader', false);
        }
      });
    }
  }
})();
