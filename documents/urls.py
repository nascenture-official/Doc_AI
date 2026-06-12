from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.DocumentListView.as_view(), name='list'),
    path('upload/', views.DocumentUploadAjaxView.as_view(), name='upload_ajax'),
    path('<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='delete'),
    path('<int:pk>/download/', views.DocumentDownloadView.as_view(), name='download'),
    path('<int:pk>/status/', views.DocumentStatusBadgeView.as_view(), name='status'),
    path('<int:pk>/detail/', views.DocumentDetailView.as_view(), name='detail'),
]
