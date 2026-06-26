import uuid

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


def default_invitation_expiry():
    return timezone.now() + timezone.timedelta(days=7)


class Workspace(models.Model):
    """A shared team space. Documents/Folders with workspace=None remain personal."""
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_workspaces')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.memberships.count()


class WorkspaceMembership(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_MEMBER, 'Member'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspace_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-role', 'joined_at']
        unique_together = ('workspace', 'user')

    def __str__(self):
        return f"{self.user} - {self.workspace} ({self.role})"


class WorkspaceInvitation(models.Model):
    # Owner role is never granted directly via invite — only via transfer-ownership.
    ROLE_CHOICES = [
        (WorkspaceMembership.ROLE_ADMIN, 'Admin'),
        (WorkspaceMembership.ROLE_MEMBER, 'Member'),
    ]
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'
    STATUS_REVOKED = 'revoked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_DECLINED, 'Declined'),
        (STATUS_REVOKED, 'Revoked'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=WorkspaceMembership.ROLE_MEMBER)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_invitation_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite {self.email} to {self.workspace} ({self.role})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class DocumentShare(models.Model):
    """Ad-hoc sharing of a single document with a specific user, independent of workspace membership."""
    PERMISSION_VIEW = 'view'
    PERMISSION_EDIT = 'edit'
    PERMISSION_CHOICES = [
        (PERMISSION_VIEW, 'Can View'),
        (PERMISSION_EDIT, 'Can Edit'),
    ]

    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='shares')
    shared_with = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_documents')
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES, default=PERMISSION_VIEW)
    shared_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents_shared')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('document', 'shared_with')

    def __str__(self):
        return f"{self.document.title} shared with {self.shared_with} ({self.permission})"
