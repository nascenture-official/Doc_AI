from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Document pages
    path('', views.DocumentListView.as_view(), name='list'),
    path('upload/', views.DocumentUploadAjaxView.as_view(), name='upload_ajax'),
    path('<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='delete'),
    path('<int:pk>/download/', views.DocumentDownloadView.as_view(), name='download'),
    path('<int:pk>/status/', views.DocumentStatusBadgeView.as_view(), name='status'),
    path('<int:pk>/detail/', views.DocumentDetailView.as_view(), name='detail'),
    path('<int:pk>/generate-summary/', views.GenerateSummaryAjaxView.as_view(), name='generate_summary'),
    path('<int:pk>/summary-status/', views.SummaryStatusAjaxView.as_view(), name='summary_status'),
    path('<int:pk>/move/', views.MoveDocumentAjaxView.as_view(), name='document_move'),

    # Folder pages
    path('folders/manage/', views.ManageFoldersView.as_view(), name='folder_manage'),
    path('folders/add/', views.FolderCreateFormView.as_view(), name='folder_add_page'),
    path('folders/<int:pk>/edit/', views.FolderEditFormView.as_view(), name='folder_edit_page'),
    path('folders/<int:pk>/', views.FolderDetailView.as_view(), name='folder_detail'),
    path('folders/api/unassigned-documents/', views.UnassignedDocumentsAjaxView.as_view(), name='api_unassigned_documents'),

    # Folder AJAX mutations — specific paths before generic <pk>
    path('folders/<int:pk>/add-documents/', views.AddDocumentsToFolderAjaxView.as_view(), name='folder_add_documents'),
    path('folders/create/', views.FolderCreateAjaxView.as_view(), name='folder_create'),
    path('folders/<int:pk>/rename/', views.FolderRenameAjaxView.as_view(), name='folder_rename'),
    path('folders/<int:pk>/delete/', views.FolderDeleteAjaxView.as_view(), name='folder_delete'),
    path('folders/<int:pk>/move/', views.FolderMoveAjaxView.as_view(), name='folder_move'),
]
