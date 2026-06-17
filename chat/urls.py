from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.ChatHomeView.as_view(), name='home'),
    path('new/', views.NewConversationView.as_view(), name='new'),
    path('sidebar/', views.SidebarConversationsView.as_view(), name='sidebar_conversations'),
    path('<int:pk>/', views.ChatDetailView.as_view(), name='detail'),
    path('<int:pk>/send/', views.SendMessageView.as_view(), name='send'),
    path('<int:pk>/messages/', views.MessageHistoryView.as_view(), name='message_history'),
    path('<int:pk>/ai-response/<int:user_msg_id>/', views.GenerateAIResponseView.as_view(), name='ai_response'),
    path('<int:pk>/stream/<int:user_msg_id>/', views.StreamAIResponseView.as_view(), name='stream_response'),
    path('<int:pk>/abort/<int:user_msg_id>/', views.AbortGenerationView.as_view(), name='abort_response'),
    path('<int:pk>/delete/', views.DeleteConversationView.as_view(), name='delete'),
]
