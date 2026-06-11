from django.contrib import admin

from .models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "created_at")
    list_filter = ("user",)
    search_fields = ("title", "user__email")
    ordering = ("-created_at",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "role", "created_at")
    list_filter = ("role", "conversation__user")
    search_fields = ("content",)
    ordering = ("-created_at",)
