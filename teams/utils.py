from django.utils.text import slugify

from .models import Workspace, WorkspaceMembership

ACTIVE_WORKSPACE_SESSION_KEY = 'active_workspace_id'


def get_active_workspace(request):
    """
    Resolves the workspace currently active in this session, re-validating membership
    on every call (membership may have been revoked since the session var was set).
    Returns None for "Personal" context.
    """
    workspace_id = request.session.get(ACTIVE_WORKSPACE_SESSION_KEY)
    if not workspace_id:
        return None

    workspace = Workspace.objects.filter(pk=workspace_id).first()
    if workspace is None:
        request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        return None

    if not WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).exists():
        request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
        return None

    return workspace


def set_active_workspace(request, workspace):
    if workspace is None:
        request.session.pop(ACTIVE_WORKSPACE_SESSION_KEY, None)
    else:
        request.session[ACTIVE_WORKSPACE_SESSION_KEY] = workspace.pk


def generate_unique_slug(name):
    base_slug = slugify(name) or 'workspace'
    slug = base_slug
    counter = 1
    while Workspace.objects.filter(slug=slug).exists():
        counter += 1
        slug = f"{base_slug}-{counter}"
    return slug
