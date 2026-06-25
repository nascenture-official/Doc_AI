from django.contrib import admin

from .models import Document, Folder, DocumentTranslation, Bookmark, Highlight, Note


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

@admin.register(DocumentTranslation)
class DocumentTranslationAdmin(admin.ModelAdmin):
    list_display = ('document', 'language', 'status', 'created_at')
    list_filter = ('status', 'language')
    search_fields = ('document__title',)


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'page_number', 'title', 'created_at')
    list_filter = ('user',)
    search_fields = ('title', 'document__title')


@admin.register(Highlight)
class HighlightAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'page_number', 'color', 'created_at')
    list_filter = ('color', 'user')
    search_fields = ('text', 'document__title')


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'page_number', 'highlight', 'created_at')
    list_filter = ('user',)
    search_fields = ('content', 'document__title')
