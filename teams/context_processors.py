from .models import WorkspaceMembership
from .permissions import pending_invitations_for
from .utils import get_active_workspace


def workspace_context(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}

    return {
        "active_workspace": get_active_workspace(request),
        "user_workspace_memberships": WorkspaceMembership.objects.filter(
            user=request.user
        ).select_related('workspace'),
        "pending_workspace_invitations": pending_invitations_for(request.user),
    }
