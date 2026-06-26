from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from .models import DocumentShare, Workspace, WorkspaceInvitation, WorkspaceMembership


def get_user_role(user, workspace):
    """Returns 'owner' | 'admin' | 'member' | None for the given user in the given workspace."""
    if workspace is None or not user.is_authenticated:
        return None
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=user).only('role').first()
    return membership.role if membership else None


def is_workspace_admin(user, workspace):
    return get_user_role(user, workspace) in (WorkspaceMembership.ROLE_OWNER, WorkspaceMembership.ROLE_ADMIN)


def is_workspace_owner(user, workspace):
    return get_user_role(user, workspace) == WorkspaceMembership.ROLE_OWNER


def visible_documents_for(user, workspace=None):
    """
    Documents the user may VIEW.
    - workspace=None  -> the user's personal documents only (today's behavior, unchanged).
    - workspace set    -> all documents inside that workspace, provided the user is a member.
    Does not include documents shared one-off via DocumentShare from a different context —
    those surface separately via the "Shared with me" view.
    """
    from documents.models import Document

    if workspace is None:
        return Document.objects.filter(user=user, workspace__isnull=True)

    if get_user_role(user, workspace) is None:
        return Document.objects.none()

    return Document.objects.filter(workspace=workspace)


def visible_folders_for(user, workspace=None):
    from documents.models import Folder

    if workspace is None:
        return Folder.objects.filter(user=user, workspace__isnull=True)

    if get_user_role(user, workspace) is None:
        return Folder.objects.none()

    return Folder.objects.filter(workspace=workspace)


def pending_invitations_for(user):
    """
    Pending, unexpired invitations addressed to this user's own email — surfaced so a user who's
    already logged in (under the invited address) sees the invite in-app, not just via the emailed link.
    """
    if not user.is_authenticated or not user.email:
        return WorkspaceInvitation.objects.none()

    return WorkspaceInvitation.objects.filter(
        email__iexact=user.email,
        status=WorkspaceInvitation.STATUS_PENDING,
        expires_at__gt=timezone.now(),
    ).select_related('workspace', 'invited_by')


def shared_with_me_documents(user):
    """Documents individually shared with this user via DocumentShare, regardless of workspace."""
    from documents.models import Document

    shared_ids = DocumentShare.objects.filter(shared_with=user).values_list('document_id', flat=True)
    return Document.objects.filter(id__in=shared_ids)


def user_can_view_document(user, document):
    if document.user_id == user.id:
        return True
    if document.workspace_id and get_user_role(user, document.workspace) is not None:
        return True
    return DocumentShare.objects.filter(document=document, shared_with=user).exists()


def user_can_edit_document(user, document):
    """Triggering AI actions / mutating the document's generated content."""
    if document.user_id == user.id:
        return True
    if document.workspace_id and is_workspace_admin(user, document.workspace):
        return True
    return DocumentShare.objects.filter(
        document=document, shared_with=user, permission=DocumentShare.PERMISSION_EDIT
    ).exists()


def user_can_delete_document(user, document):
    """Deleting, moving, or renaming — never grantable via DocumentShare."""
    if document.user_id == user.id:
        return True
    if document.workspace_id and is_workspace_admin(user, document.workspace):
        return True
    return False


def user_can_manage_shares(user, document):
    """Who can add/remove/change DocumentShare entries on a document."""
    return user_can_delete_document(user, document)


# Folders have no per-folder ad-hoc sharing (DocumentShare is document-only) — visibility and
# edit rights come purely from ownership or workspace membership/role.

def user_can_view_folder(user, folder):
    if folder.user_id == user.id:
        return True
    return bool(folder.workspace_id and get_user_role(user, folder.workspace) is not None)


def user_can_edit_folder(user, folder):
    """Renaming, moving, or deleting a folder — Members may only manage folders they created."""
    if folder.user_id == user.id:
        return True
    return bool(folder.workspace_id and is_workspace_admin(user, folder.workspace))


def get_viewable_document_or_404(user, pk):
    from documents.models import Document
    document = get_object_or_404(Document, pk=pk)
    if not user_can_view_document(user, document):
        raise Http404("Document not found.")
    return document


def get_editable_document_or_404(user, pk):
    from documents.models import Document
    document = get_object_or_404(Document, pk=pk)
    if not user_can_edit_document(user, document):
        raise Http404("Document not found.")
    return document


def get_deletable_document_or_404(user, pk):
    from documents.models import Document
    document = get_object_or_404(Document, pk=pk)
    if not user_can_delete_document(user, document):
        raise Http404("Document not found.")
    return document


def get_viewable_folder_or_404(user, pk):
    from documents.models import Folder
    folder = get_object_or_404(Folder, pk=pk)
    if not user_can_view_folder(user, folder):
        raise Http404("Folder not found.")
    return folder


def get_editable_folder_or_404(user, pk):
    from documents.models import Folder
    folder = get_object_or_404(Folder, pk=pk)
    if not user_can_edit_folder(user, folder):
        raise Http404("Folder not found.")
    return folder


class _WorkspaceRoleRequiredMixin(LoginRequiredMixin):
    """
    Resolves self.workspace from URL kwarg 'pk' and self.user_role for the requester.
    Performs all checks BEFORE the view's get()/post()/etc. ever runs — subclasses only
    set `minimum_role`, they must not re-wrap dispatch() with their own super() chain
    (a naive override-and-call-super() pattern here would run the handler first and
    only reject it after side effects already happened).
    """
    login_url = "/accounts/login/"
    minimum_role = None  # None = any member, 'admin' = owner+admin, 'owner' = owner only

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        self.workspace = get_object_or_404(Workspace, pk=kwargs.get('pk'))
        self.user_role = get_user_role(request.user, self.workspace)

        if self.user_role is None:
            return JsonResponse({"success": False, "error": "You are not a member of this workspace."}, status=403)
        if self.minimum_role == 'admin' and self.user_role not in (WorkspaceMembership.ROLE_OWNER, WorkspaceMembership.ROLE_ADMIN):
            return JsonResponse({"success": False, "error": "Admin or Owner role required."}, status=403)
        if self.minimum_role == 'owner' and self.user_role != WorkspaceMembership.ROLE_OWNER:
            return JsonResponse({"success": False, "error": "Owner role required."}, status=403)

        # All checks passed — go straight to the concrete View's dispatch (get/post/etc.)
        return View.dispatch(self, request, *args, **kwargs)


class WorkspaceAccessRequiredMixin(_WorkspaceRoleRequiredMixin):
    minimum_role = None


class WorkspaceAdminRequiredMixin(_WorkspaceRoleRequiredMixin):
    minimum_role = 'admin'


class WorkspaceOwnerRequiredMixin(_WorkspaceRoleRequiredMixin):
    minimum_role = 'owner'
