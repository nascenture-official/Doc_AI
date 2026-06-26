from django.urls import path
from . import views

app_name = 'teams'

urlpatterns = [
    path('', views.WorkspaceListView.as_view(), name='list'),
    path('create/', views.WorkspaceCreateAjaxView.as_view(), name='create'),
    path('switch/', views.SwitchWorkspaceView.as_view(), name='switch'),
    path('shared-with-me/', views.SharedWithMeView.as_view(), name='shared_with_me'),

    path('<int:pk>/', views.WorkspaceDetailView.as_view(), name='detail'),
    path('<int:pk>/rename/', views.WorkspaceRenameAjaxView.as_view(), name='rename'),
    path('<int:pk>/delete/', views.WorkspaceDeleteView.as_view(), name='delete'),
    path('<int:pk>/leave/', views.WorkspaceLeaveView.as_view(), name='leave'),
    path('<int:pk>/transfer-ownership/', views.TransferOwnershipAjaxView.as_view(), name='transfer_ownership'),
    path('<int:pk>/invite/', views.InviteMemberAjaxView.as_view(), name='invite'),
    path('<int:pk>/members/<int:user_id>/role/', views.ChangeMemberRoleAjaxView.as_view(), name='change_role'),
    path('<int:pk>/members/<int:user_id>/remove/', views.RemoveMemberAjaxView.as_view(), name='remove_member'),

    path('invitations/<uuid:token>/accept/', views.AcceptInvitationView.as_view(), name='accept_invite'),
    path('invitations/<uuid:token>/decline/', views.DeclineInvitationView.as_view(), name='decline_invite'),
    path('invitations/<int:pk>/revoke/', views.RevokeInvitationAjaxView.as_view(), name='revoke_invite'),

    path('documents/<int:pk>/shares/', views.DocumentSharesAjaxView.as_view(), name='document_shares'),
    path('documents/<int:pk>/shares/<int:share_id>/', views.DocumentShareDetailAjaxView.as_view(), name='document_share_detail'),
]
