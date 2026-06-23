from django.contrib import admin

from .models import Document, Folder


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'user', 'document_count', 'created_at')
    list_filter = ('user',)
    search_fields = ('name',)
    raw_id_fields = ('parent',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'folder', 'status', 'uploaded_at')
    list_filter = ('status', 'folder')
    search_fields = ('title',)
