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
    path('<int:pk>/translate/', views.TranslateDocumentAjaxView.as_view(), name='translate'),
    path('<int:pk>/translation-status/', views.TranslationStatusAjaxView.as_view(), name='translation_status'),
    path('<int:pk>/rewrite/', views.RewriteContentAjaxView.as_view(), name='rewrite'),
    path('<int:pk>/rewrite-status/', views.RewriteStatusAjaxView.as_view(), name='rewrite_status'),
    path('<int:pk>/extract-key-points/', views.ExtractKeyPointsAjaxView.as_view(), name='extract_key_points'),
    path('<int:pk>/key-points-status/', views.KeyPointsStatusAjaxView.as_view(), name='key_points_status'),
    path('<int:pk>/generate-faqs/', views.GenerateFAQsAjaxView.as_view(), name='generate_faqs'),
    path('<int:pk>/faqs-status/', views.FAQsStatusAjaxView.as_view(), name='faqs_status'),
    path('<int:pk>/move/', views.MoveDocumentAjaxView.as_view(), name='document_move'),
    path('<int:pk>/compare/', views.DocumentCompareCreateView.as_view(), name='compare_create'),
    path('compare/<int:comparison_id>/', views.ComparisonDetailView.as_view(), name='comparison_detail'),
    path('compare/<int:comparison_id>/status/', views.ComparisonStatusAjaxView.as_view(), name='comparison_status'),
    
    # Reader and annotations
    path('<int:pk>/reader/', views.DocumentReaderView.as_view(), name='reader'),
    path('<int:pk>/annotations/', views.AnnotationsAjaxView.as_view(), name='annotations'),
    path('<int:pk>/bookmarks/', views.BookmarksAjaxView.as_view(), name='bookmarks'),
    path('<int:pk>/highlights/', views.HighlightsAjaxView.as_view(), name='highlights'),
    path('<int:pk>/highlights/<int:highlight_id>/delete/', views.HighlightsAjaxView.as_view(), name='highlight_delete'),
    path('<int:pk>/notes/', views.NotesAjaxView.as_view(), name='notes'),
    path('<int:pk>/notes/<int:note_id>/delete/', views.NotesAjaxView.as_view(), name='note_delete'),
    path('<int:pk>/notes/search/', views.NotesSearchAjaxView.as_view(), name='notes_search'),

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
