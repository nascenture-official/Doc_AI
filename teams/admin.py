from django.contrib import admin

from .models import DocumentShare, Workspace, WorkspaceInvitation, WorkspaceMembership


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'owner', 'created_at')
    search_fields = ('name', 'slug', 'owner__username', 'owner__email')


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'user', 'role', 'joined_at')
    list_filter = ('role',)


@admin.register(WorkspaceInvitation)
class WorkspaceInvitationAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'email', 'role', 'status', 'invited_by', 'created_at', 'expires_at')
    list_filter = ('status', 'role')


@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
    list_display = ('document', 'shared_with', 'permission', 'shared_by', 'created_at')
    list_filter = ('permission',)
