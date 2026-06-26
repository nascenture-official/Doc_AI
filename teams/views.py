from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from .models import DocumentShare, Workspace, WorkspaceInvitation, WorkspaceMembership
from .permissions import (
    WorkspaceAccessRequiredMixin,
    WorkspaceAdminRequiredMixin,
    WorkspaceOwnerRequiredMixin,
    get_user_role,
    is_workspace_admin,
    shared_with_me_documents,
    user_can_manage_shares,
)
from .utils import generate_unique_slug, get_active_workspace, set_active_workspace


def _safe_next_url(request):
    next_url = request.POST.get('next', '').strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return next_url
    return None


def _send_invitation_email(request, invitation):
    accept_url = request.build_absolute_uri(
        reverse('teams:accept_invite', kwargs={'token': invitation.token})
    )
    context = {
        'invitation': invitation,
        'workspace': invitation.workspace,
        'inviter': invitation.invited_by,
        'accept_url': accept_url,
    }
    subject = render_to_string('teams/email/invitation_subject.txt', context).strip()
    html_body = render_to_string('teams/email/invitation_message.html', context)
    send_mail(
        subject=subject,
        message=f"You've been invited to join the workspace '{invitation.workspace.name}'. Open this link to accept: {accept_url}",
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[invitation.email],
        html_message=html_body,
        fail_silently=True,
    )


# ─── Workspace CRUD ─────────────────────────────────────────────────────────

class WorkspaceListView(LoginRequiredMixin, View):
    login_url = "/accounts/login/"
    template_name = "teams/list.html"

    def get(self, request):
        memberships = WorkspaceMembership.objects.filter(user=request.user).select_related('workspace')
        active_workspace = get_active_workspace(request)
        return render(request, self.template_name, {
            "memberships": memberships,
            "active_workspace": active_workspace,
            "page_title": "Workspaces",
        })


class WorkspaceCreateAjaxView(LoginRequiredMixin, View):
    login_url = "/accounts/login/"

    def post(self, request):
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({"success": False, "error": "Workspace name is required."}, status=400)

        workspace = Workspace.objects.create(name=name, slug=generate_unique_slug(name), owner=request.user)
        WorkspaceMembership.objects.create(workspace=workspace, user=request.user, role=WorkspaceMembership.ROLE_OWNER)

        return JsonResponse({
            "success": True,
            "id": workspace.pk,
            "name": workspace.name,
            "url": reverse('teams:detail', kwargs={'pk': workspace.pk}),
        })


class SwitchWorkspaceView(LoginRequiredMixin, View):
    """POST workspace_id='' for Personal, or a workspace pk the user is a member of."""
    login_url = "/accounts/login/"

    def post(self, request):
        workspace_id = request.POST.get('workspace_id', '').strip()
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('dashboard')

        if not workspace_id:
            set_active_workspace(request, None)
            return redirect(next_url)

        workspace = get_object_or_404(Workspace, pk=workspace_id)
        if get_user_role(request.user, workspace) is None:
            messages.error(request, "You are not a member of that workspace.")
            return redirect(next_url)

        set_active_workspace(request, workspace)
        return redirect(next_url)


class WorkspaceDetailView(WorkspaceAccessRequiredMixin, View):
    template_name = "teams/detail.html"

    def get(self, request, pk):
        members = self.workspace.memberships.select_related('user').all()
        pending_invitations = self.workspace.invitations.filter(status=WorkspaceInvitation.STATUS_PENDING)
        return render(request, self.template_name, {
            "workspace": self.workspace,
            "members": members,
            "pending_invitations": pending_invitations,
            "user_role": self.user_role,
            "can_manage": self.user_role in (WorkspaceMembership.ROLE_OWNER, WorkspaceMembership.ROLE_ADMIN),
            "page_title": self.workspace.name,
        })


class WorkspaceRenameAjaxView(WorkspaceOwnerRequiredMixin, View):
    def post(self, request, pk):
        name = request.POST.get('name', '').strip()
        if not name:
            return JsonResponse({"success": False, "error": "Workspace name cannot be empty."}, status=400)
        self.workspace.name = name
        self.workspace.save(update_fields=['name'])
        return JsonResponse({"success": True, "name": self.workspace.name})


class WorkspaceDeleteView(WorkspaceOwnerRequiredMixin, View):
    """Deletes the workspace. Documents/Folders survive — SET_NULL reverts them to personal."""

    def post(self, request, pk):
        self.workspace.delete()
        messages.success(request, "Workspace deleted. Its documents were kept and returned to their uploaders' personal spaces.")
        return redirect('teams:list')


class WorkspaceLeaveView(WorkspaceAccessRequiredMixin, View):
    def post(self, request, pk):
        if self.user_role == WorkspaceMembership.ROLE_OWNER:
            messages.error(request, "Transfer ownership to another member before leaving.")
            return redirect('teams:detail', pk=pk)
        WorkspaceMembership.objects.filter(workspace=self.workspace, user=request.user).delete()
        messages.success(request, f"You left {self.workspace.name}.")
        return redirect('teams:list')


class TransferOwnershipAjaxView(WorkspaceOwnerRequiredMixin, View):
    def post(self, request, pk):
        new_owner_id = request.POST.get('user_id', '').strip()
        new_owner_membership = WorkspaceMembership.objects.filter(workspace=self.workspace, user_id=new_owner_id).first()
        if new_owner_membership is None:
            return JsonResponse({"success": False, "error": "That user is not a member of this workspace."}, status=400)

        old_owner_membership = WorkspaceMembership.objects.get(workspace=self.workspace, user=request.user)
        old_owner_membership.role = WorkspaceMembership.ROLE_ADMIN
        old_owner_membership.save(update_fields=['role'])

        new_owner_membership.role = WorkspaceMembership.ROLE_OWNER
        new_owner_membership.save(update_fields=['role'])

        self.workspace.owner = new_owner_membership.user
        self.workspace.save(update_fields=['owner'])

        return JsonResponse({"success": True})


# ─── Membership management ─────────────────────────────────────────────────

class InviteMemberAjaxView(WorkspaceAdminRequiredMixin, View):
    def post(self, request, pk):
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role', WorkspaceMembership.ROLE_MEMBER)

        if not email:
            return JsonResponse({"success": False, "error": "Email is required."}, status=400)
        if role not in dict(WorkspaceInvitation.ROLE_CHOICES):
            return JsonResponse({"success": False, "error": "Invalid role."}, status=400)
        if WorkspaceMembership.objects.filter(workspace=self.workspace, user__email__iexact=email).exists():
            return JsonResponse({"success": False, "error": "This person is already a member."}, status=400)

        invitation = WorkspaceInvitation.objects.filter(
            workspace=self.workspace, email__iexact=email, status=WorkspaceInvitation.STATUS_PENDING
        ).first()
        if invitation is None:
            invitation = WorkspaceInvitation.objects.create(
                workspace=self.workspace, email=email, role=role, invited_by=request.user
            )
        else:
            invitation.role = role
            invitation.invited_by = request.user
            invitation.save(update_fields=['role', 'invited_by'])

        _send_invitation_email(request, invitation)

        return JsonResponse({
            "success": True,
            "invitation": {"id": invitation.pk, "email": invitation.email, "role": invitation.get_role_display()},
        })


class ChangeMemberRoleAjaxView(WorkspaceAdminRequiredMixin, View):
    def post(self, request, pk, user_id):
        membership = get_object_or_404(WorkspaceMembership, workspace=self.workspace, user_id=user_id)
        if membership.role == WorkspaceMembership.ROLE_OWNER:
            return JsonResponse({"success": False, "error": "Use Transfer Ownership to change the Owner."}, status=400)

        new_role = request.POST.get('role', '').strip()
        if new_role not in (WorkspaceMembership.ROLE_ADMIN, WorkspaceMembership.ROLE_MEMBER):
            return JsonResponse({"success": False, "error": "Invalid role."}, status=400)

        membership.role = new_role
        membership.save(update_fields=['role'])
        return JsonResponse({"success": True, "role": membership.get_role_display()})


class RemoveMemberAjaxView(WorkspaceAdminRequiredMixin, View):
    def post(self, request, pk, user_id):
        membership = get_object_or_404(WorkspaceMembership, workspace=self.workspace, user_id=user_id)
        if membership.role == WorkspaceMembership.ROLE_OWNER:
            return JsonResponse({"success": False, "error": "The Owner cannot be removed. Transfer ownership first."}, status=400)

        membership.delete()
        return JsonResponse({"success": True})


# ─── Invitations ────────────────────────────────────────────────────────────

class AcceptInvitationView(View):
    template_name = "teams/accept_invite.html"

    def _get_invitation(self, token):
        return get_object_or_404(WorkspaceInvitation, token=token)

    def get(self, request, token):
        invitation = self._get_invitation(token)

        if invitation.status != WorkspaceInvitation.STATUS_PENDING or invitation.is_expired:
            return render(request, self.template_name, {"invitation": invitation, "invalid": True})

        if not request.user.is_authenticated:
            signup_url = reverse('account_signup')
            return redirect(f"{signup_url}?next={request.path}&email={invitation.email}")

        email_mismatch = request.user.email.lower() != invitation.email.lower()
        return render(request, self.template_name, {
            "invitation": invitation,
            "invalid": False,
            "email_mismatch": email_mismatch,
        })

    def post(self, request, token):
        invitation = self._get_invitation(token)
        next_url = _safe_next_url(request)

        if not request.user.is_authenticated:
            return redirect('account_login')
        if invitation.status != WorkspaceInvitation.STATUS_PENDING or invitation.is_expired:
            messages.error(request, "This invitation is no longer valid.")
            return redirect(next_url or 'teams:list')
        if request.user.email.lower() != invitation.email.lower():
            messages.error(request, "This invitation was sent to a different email address.")
            return redirect(next_url or 'teams:list')

        WorkspaceMembership.objects.get_or_create(
            workspace=invitation.workspace, user=request.user, defaults={'role': invitation.role}
        )
        invitation.status = WorkspaceInvitation.STATUS_ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['status', 'accepted_at'])

        messages.success(request, f"You've joined {invitation.workspace.name}.")
        return redirect(next_url) if next_url else redirect('teams:detail', pk=invitation.workspace_id)


class DeclineInvitationView(View):
    def post(self, request, token):
        invitation = get_object_or_404(WorkspaceInvitation, token=token)
        if invitation.status == WorkspaceInvitation.STATUS_PENDING:
            invitation.status = WorkspaceInvitation.STATUS_DECLINED
            invitation.save(update_fields=['status'])
        messages.info(request, "Invitation declined.")
        if not request.user.is_authenticated:
            return redirect('account_login')
        next_url = _safe_next_url(request)
        return redirect(next_url) if next_url else redirect('teams:list')


class RevokeInvitationAjaxView(LoginRequiredMixin, View):
    """pk here is the WorkspaceInvitation pk, not a Workspace pk — role check resolved manually."""
    login_url = "/accounts/login/"

    def post(self, request, pk):
        invitation = get_object_or_404(WorkspaceInvitation, pk=pk)
        if not is_workspace_admin(request.user, invitation.workspace):
            return JsonResponse({"success": False, "error": "Admin or Owner role required."}, status=403)

        invitation.status = WorkspaceInvitation.STATUS_REVOKED
        invitation.save(update_fields=['status'])
        return JsonResponse({"success": True})


# ─── Document sharing ───────────────────────────────────────────────────────

class DocumentSharesAjaxView(LoginRequiredMixin, View):
    login_url = "/accounts/login/"

    def _get_document(self, pk):
        from documents.models import Document
        return get_object_or_404(Document, pk=pk)

    def get(self, request, pk):
        document = self._get_document(pk)
        if not user_can_manage_shares(request.user, document):
            return JsonResponse({"success": False, "error": "You cannot manage sharing on this document."}, status=403)

        shares = document.shares.select_related('shared_with').all()
        return JsonResponse({
            "success": True,
            "shares": [
                {"id": s.pk, "email": s.shared_with.email, "name": s.shared_with.get_full_name() or s.shared_with.username,
                 "permission": s.permission}
                for s in shares
            ],
        })

    def post(self, request, pk):
        document = self._get_document(pk)
        if not user_can_manage_shares(request.user, document):
            return JsonResponse({"success": False, "error": "You cannot manage sharing on this document."}, status=403)

        email = request.POST.get('email', '').strip().lower()
        permission = request.POST.get('permission', DocumentShare.PERMISSION_VIEW)
        if permission not in dict(DocumentShare.PERMISSION_CHOICES):
            return JsonResponse({"success": False, "error": "Invalid permission."}, status=400)

        target_user = User.objects.filter(email__iexact=email).first()
        if target_user is None:
            return JsonResponse({"success": False, "error": "No registered user with that email."}, status=404)
        if target_user.id == document.user_id:
            return JsonResponse({"success": False, "error": "This user already owns the document."}, status=400)

        share, _created = DocumentShare.objects.update_or_create(
            document=document, shared_with=target_user,
            defaults={'permission': permission, 'shared_by': request.user},
        )
        return JsonResponse({
            "success": True,
            "share": {"id": share.pk, "email": target_user.email,
                      "name": target_user.get_full_name() or target_user.username, "permission": share.permission},
        })


class DocumentShareDetailAjaxView(LoginRequiredMixin, View):
    login_url = "/accounts/login/"

    def _get_share(self, pk, share_id):
        from documents.models import Document
        document = get_object_or_404(Document, pk=pk)
        share = get_object_or_404(DocumentShare, pk=share_id, document=document)
        return document, share

    def post(self, request, pk, share_id):
        """Browsers can't send PATCH from a plain form — accept POST with _method=PATCH for permission changes."""
        document, share = self._get_share(pk, share_id)
        if not user_can_manage_shares(request.user, document):
            return JsonResponse({"success": False, "error": "You cannot manage sharing on this document."}, status=403)

        permission = request.POST.get('permission')
        if permission not in dict(DocumentShare.PERMISSION_CHOICES):
            return JsonResponse({"success": False, "error": "Invalid permission."}, status=400)

        share.permission = permission
        share.save(update_fields=['permission'])
        return JsonResponse({"success": True})

    def delete(self, request, pk, share_id):
        document, share = self._get_share(pk, share_id)
        if not user_can_manage_shares(request.user, document):
            return JsonResponse({"success": False, "error": "You cannot manage sharing on this document."}, status=403)

        share.delete()
        return JsonResponse({"success": True})


class SharedWithMeView(LoginRequiredMixin, View):
    login_url = "/accounts/login/"
    template_name = "teams/shared_with_me.html"

    def get(self, request):
        documents = shared_with_me_documents(request.user).select_related('user').defer(
            'summary_short', 'summary_long', 'error_message'
        )
        permissions_by_doc_id = dict(
            DocumentShare.objects.filter(shared_with=request.user).values_list('document_id', 'permission')
        )
        for doc in documents:
            doc.my_permission = permissions_by_doc_id.get(doc.id, DocumentShare.PERMISSION_VIEW)

        return render(request, self.template_name, {
            "documents": documents,
            "page_title": "Shared with Me",
        })
