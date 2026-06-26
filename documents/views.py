import time
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse, FileResponse, Http404
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_protect

from django_q.tasks import async_task

from .models import Document, Folder, DocumentComparison, Bookmark, Highlight, Note
from django.db.models import Q
import json
from .services.vector_store import delete_vector_index
from teams.utils import get_active_workspace
from teams.permissions import (
    visible_documents_for,
    visible_folders_for,
    get_viewable_document_or_404,
    get_editable_document_or_404,
    get_deletable_document_or_404,
    get_viewable_folder_or_404,
    get_editable_folder_or_404,
    is_workspace_admin,
    user_can_delete_document,
    user_can_edit_folder,
)

DOCUMENTS_PAGE_SIZE = 12


class DocumentListView(LoginRequiredMixin, View):
    """
    Renders the page listing all documents owned by the current user.
    Accepts ?folder=<id> to filter by folder. Passes root_folders for the sidebar tree.
    Paginates 12 documents per page. Defers heavy fields (summaries) not needed on list view.
    """
    login_url = "/accounts/login/"
    template_name = "documents/list.html"

    def get(self, request):
        folder_id = request.GET.get('folder')
        current_folder = None
        active_workspace = get_active_workspace(request)

        documents_qs = visible_documents_for(request.user, active_workspace).defer(
            'summary_short', 'summary_long', 'error_message'
        )

        if folder_id:
            try:
                current_folder = visible_folders_for(request.user, active_workspace).get(pk=folder_id)
                documents_qs = documents_qs.filter(folder=current_folder)
            except Folder.DoesNotExist:
                current_folder = None
        elif 'folder' in request.GET and request.GET['folder'] == '':
            # Explicit empty string → show unorganized docs (folder=NULL)
            documents_qs = documents_qs.filter(folder__isnull=True)

        paginator = Paginator(documents_qs, DOCUMENTS_PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        root_folders = visible_folders_for(request.user, active_workspace).filter(parent__isnull=True)

        # Workspace docs uploaded by someone else are visible but not deletable by a plain
        # Member — annotate so the table can hide the delete checkbox/button per row instead
        # of letting them select it and hit a silent 404 on confirm.
        for doc in page_obj:
            doc.can_delete = user_can_delete_document(request.user, doc)

        return render(request, self.template_name, {
            "documents": page_obj,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "page_title": "My Documents",
            "root_folders": root_folders,
            "current_folder": current_folder,
            "active_workspace": active_workspace,
        })


class DocumentUploadAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX file uploads. Validates the PDF file, saves it,
    enqueues background task for text extraction + embedding processing,
    and returns initial document details.
    """
    login_url = "/accounts/login/"

    def post(self, request):
        if 'file' not in request.FILES:
            return JsonResponse({"success": False, "error": "No file uploaded."}, status=400)

        file = request.FILES['file']
        
        # 1. Size Validation (Max 20MB)
        max_size = 100 * 1024 * 1024  # 20MB
        if file.size > max_size:
            return JsonResponse({"success": False, "error": "File size exceeds the 20MB limit."}, status=400)

        # 2. Type Validation (PDF Only)
        if not file.name.lower().endswith('.pdf'):
            return JsonResponse({"success": False, "error": "Only PDF files are allowed."}, status=400)

        # 3. Save initial document in "uploading" state
        doc = Document(
            user=request.user,
            workspace=get_active_workspace(request),
            title=file.name,
            file=file,
            file_size=file.size,
            status='uploading'
        )
        doc.save()

        # 4. Enqueue background RAG processing task via Django Q
        try:
            # Set status to processing before enqueuing
            doc.status = 'processing'
            doc.save()

            # Enqueue task through Django Q so it is tracked in the admin panel
            async_task(
                'documents.tasks.process_uploaded_document',
                doc.id,
                task_name=f"process_doc_{doc.id}"
            )
        except Exception as e:
            doc.status = 'failed'
            doc.error_message = f"Task queue error: {str(e)}"
            doc.save()
            return JsonResponse({
                "success": False,
                "error": doc.error_message,
                "id": doc.id,
                "status": doc.status
            }, status=500)

        return JsonResponse({
            "success": True,
            "id": doc.id,
            "title": doc.title,
            "page_count": doc.page_count,
            "file_size": doc.file_size,
            "status": doc.status,
            "uploaded_at": doc.uploaded_at.strftime('%b %d, %Y, %I:%M %p')
        })

class DocumentStatusBadgeView(LoginRequiredMixin, View):
    """
    HTMX Polling endpoint. Returns HTML snippet showing processing status.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        return render(request, "documents/_status_badge.html", {"doc": doc, "is_htmx": True})

class DocumentDetailView(LoginRequiredMixin, View):
    """
    Renders detailed view of a document including its summaries and metadata.
    """
    login_url = "/accounts/login/"
    template_name = "documents/detail.html"

    def get(self, request, pk):
        from documents.models import TRANSLATION_LANGUAGES
        from teams.permissions import user_can_edit_document, user_can_delete_document, user_can_manage_shares

        doc = get_viewable_document_or_404(request.user, pk)
        all_documents = visible_documents_for(request.user, doc.workspace).exclude(id=doc.id).order_by('-uploaded_at')
        return render(request, self.template_name, {
            "document": doc,
            "all_documents": all_documents,
            "page_title": f"Document: {doc.title}",
            "translation_languages": TRANSLATION_LANGUAGES,
            "can_edit_document": user_can_edit_document(request.user, doc),
            "can_delete_document": user_can_delete_document(request.user, doc),
            "can_manage_shares": user_can_manage_shares(request.user, doc),
        })

class DocumentDeleteView(LoginRequiredMixin, View):
    """
    Deletes the document record, deletes its corresponding PDF from storage,
    and removes its corresponding FAISS vector index files from disk.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_deletable_document_or_404(request.user, pk)
        try:
            # Delete vectors from Chroma DB
            delete_vector_index(doc.id)
            # Delete file on disk
            if doc.file:
                doc.file.delete(save=False)
            doc.delete()
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

class DocumentDownloadView(LoginRequiredMixin, View):
    """
    Securely serves the PDF file as an attachment.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        try:
            response = FileResponse(doc.file.open('rb'), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{doc.title}"'
            return response
        except Exception:
            messages.error(request, "Could not retrieve the file.")
            return redirect('documents:list')

class GenerateSummaryAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to trigger on-demand summary generation.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_editable_document_or_404(request.user, pk)
        summary_type = request.POST.get('type')
        
        if summary_type not in ['short', 'detailed']:
            return JsonResponse({"success": False, "error": "Invalid summary type."}, status=400)
            
        try:
            async_task(
                'documents.tasks.generate_summary_task',
                doc.id,
                summary_type,
                task_name=f"generate_{summary_type}_summary_{doc.id}"
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

class SummaryStatusAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to poll for summary generation status.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        from documents.templatetags.markdown_extras import markdown_to_html
        
        doc = get_viewable_document_or_404(request.user, pk)
        summary_type = request.GET.get('type')
        
        if summary_type == 'short':
            content = doc.summary_short
        elif summary_type == 'detailed':
            content = doc.summary_long
        else:
            return JsonResponse({"success": False, "error": "Invalid summary type."}, status=400)
            
        if content:
            # Check if it failed
            if content.startswith("Failed to generate"):
                return JsonResponse({"success": False, "error": content})
            return JsonResponse({"success": True, "content": markdown_to_html(content)})
        else:
            return JsonResponse({"success": True, "status": "processing"})


class TranslateDocumentAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to trigger document translation.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_editable_document_or_404(request.user, pk)
        language = request.POST.get('language')
        
        from documents.models import TRANSLATION_LANGUAGES
        if language not in dict(TRANSLATION_LANGUAGES).keys():
            return JsonResponse({"success": False, "error": "Invalid language selected."}, status=400)
            
        try:
            async_task(
                'documents.tasks.translate_document_task',
                doc.id,
                language,
                task_name=f"translate_doc_{doc.id}_{language}"
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

class TranslationStatusAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to poll for translation status.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        from documents.templatetags.markdown_extras import markdown_to_html
        from documents.models import DocumentTranslation
        
        doc = get_viewable_document_or_404(request.user, pk)
        language = request.GET.get('language')
        
        try:
            translation = DocumentTranslation.objects.get(document=doc, language=language)
            if translation.status == 'ready' and translation.translated_text:
                return JsonResponse({"success": True, "content": markdown_to_html(translation.translated_text)})
            elif translation.status == 'failed':
                return JsonResponse({"success": False, "error": translation.error_message or "Translation failed."})
            else:
                return JsonResponse({"success": True, "status": "processing"})
        except DocumentTranslation.DoesNotExist:
            return JsonResponse({"success": True, "status": "processing"})

# ─── Folder Views ─────────────────────────────────────────────────────────────

class FolderDetailView(LoginRequiredMixin, View):
    """
    Shows all documents directly inside a specific folder, along with its
    direct child subfolders and a breadcrumb for navigation.
    """
    login_url = "/accounts/login/"
    template_name = "documents/folder_detail.html"

    def get(self, request, pk):
        folder = get_viewable_folder_or_404(request.user, pk)

        documents_qs = visible_documents_for(request.user, folder.workspace).filter(
            folder=folder
        ).defer('summary_short', 'summary_long', 'error_message')

        paginator = Paginator(documents_qs, DOCUMENTS_PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # "Remove from folder" uses the same delete permission as the document itself.
        for doc in page_obj:
            doc.can_delete = user_can_delete_document(request.user, doc)

        root_folders = visible_folders_for(request.user, folder.workspace).filter(parent__isnull=True)

        # Rename/Delete/Add-document all require edit rights on the folder itself — annotate so
        # the template can hide those controls instead of letting a view-only Member hit a 404.
        subfolders = list(visible_folders_for(request.user, folder.workspace).filter(parent=folder))
        for sub in subfolders:
            sub.can_edit = user_can_edit_folder(request.user, sub)

        return render(request, self.template_name, {
            "folder": folder,
            "documents": page_obj,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "subfolders": subfolders,
            "breadcrumb": folder.get_breadcrumb(),
            "root_folders": root_folders,
            "current_folder": folder,
            "can_edit_folder": user_can_edit_folder(request.user, folder),
            "page_title": folder.name,
        })


class FolderCreateAjaxView(LoginRequiredMixin, View):
    """
    AJAX: Creates a new folder. Accepts name + optional parent_id.
    Returns JSON with folder id, name, and detail URL.
    """
    login_url = "/accounts/login/"

    def post(self, request):
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id', '').strip()

        if not name:
            return JsonResponse({"success": False, "error": "Folder name is required."}, status=400)

        parent = None
        workspace = get_active_workspace(request)
        if parent_id:
            try:
                parent = get_viewable_folder_or_404(request.user, parent_id)
            except Http404:
                return JsonResponse({"success": False, "error": "Parent folder not found."}, status=404)
            workspace = parent.workspace

        # Check uniqueness — scoped by workspace for shared folders, by user for personal ones
        if workspace:
            duplicate_exists = Folder.objects.filter(workspace=workspace, name=name, parent=parent).exists()
        else:
            duplicate_exists = Folder.objects.filter(user=request.user, workspace__isnull=True, name=name, parent=parent).exists()
        if duplicate_exists:
            return JsonResponse({"success": False, "error": "A folder with this name already exists here."}, status=400)

        folder = Folder.objects.create(user=request.user, workspace=workspace, name=name, parent=parent)
        return JsonResponse({
            "success": True,
            "id": folder.pk,
            "name": folder.name,
            "url": f"/documents/folders/{folder.pk}/",
            "parent_id": parent.pk if parent else None,
        })


class FolderRenameAjaxView(LoginRequiredMixin, View):
    """
    AJAX: Renames a folder owned by the current user.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        folder = get_editable_folder_or_404(request.user, pk)
        name = request.POST.get('name', '').strip()

        if not name:
            return JsonResponse({"success": False, "error": "Folder name cannot be empty."}, status=400)

        # Check uniqueness in the same parent — scoped by workspace for shared folders, by user for personal ones
        if folder.workspace:
            qs = Folder.objects.filter(workspace=folder.workspace, name=name, parent=folder.parent).exclude(pk=pk)
        else:
            qs = Folder.objects.filter(user=request.user, workspace__isnull=True, name=name, parent=folder.parent).exclude(pk=pk)
        if qs.exists():
            return JsonResponse({"success": False, "error": "A folder with this name already exists here."}, status=400)

        folder.name = name
        folder.save(update_fields=['name', 'updated_at'])
        return JsonResponse({"success": True, "name": folder.name})


class FolderDeleteAjaxView(LoginRequiredMixin, View):
    """
    AJAX: Deletes a folder and all its descendant folders (CASCADE).
    Documents inside those folders are orphaned (SET_NULL) — never deleted.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        folder = get_editable_folder_or_404(request.user, pk)
        parent_id = folder.parent_id  # Return for UI re-render
        folder.delete()
        return JsonResponse({"success": True, "parent_id": parent_id})


class FolderMoveAjaxView(LoginRequiredMixin, View):
    """
    AJAX: Moves a folder to a new parent.
    Blocks moving a folder into one of its own descendants.
    Pass new_parent_id='' to move to root.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        folder = get_editable_folder_or_404(request.user, pk)
        new_parent_id = request.POST.get('new_parent_id', '').strip()

        new_parent = None
        if new_parent_id:
            try:
                new_parent = get_viewable_folder_or_404(request.user, new_parent_id)
            except Http404:
                return JsonResponse({"success": False, "error": "Target folder not found."}, status=404)

            # Guard: cannot move into own descendant
            if folder.pk == new_parent.pk or folder.is_ancestor_of(new_parent):
                return JsonResponse({
                    "success": False,
                    "error": "Cannot move a folder into itself or one of its subfolders."
                }, status=400)

            # Guard: cannot move a folder across workspace boundaries
            if new_parent.workspace_id != folder.workspace_id:
                return JsonResponse({
                    "success": False,
                    "error": "Cannot move a folder into a different workspace."
                }, status=400)

        # Check name uniqueness at new location — scoped by workspace for shared folders, by user for personal ones
        if folder.workspace:
            duplicate_exists = Folder.objects.filter(workspace=folder.workspace, name=folder.name, parent=new_parent).exclude(pk=pk).exists()
        else:
            duplicate_exists = Folder.objects.filter(user=request.user, workspace__isnull=True, name=folder.name, parent=new_parent).exclude(pk=pk).exists()
        if duplicate_exists:
            return JsonResponse({
                "success": False,
                "error": f'A folder named "{folder.name}" already exists in the target location.'
            }, status=400)

        folder.parent = new_parent
        folder.save(update_fields=['parent', 'updated_at'])
        return JsonResponse({"success": True, "new_parent_id": new_parent.pk if new_parent else None})


class MoveDocumentAjaxView(LoginRequiredMixin, View):
    """
    AJAX: Assigns a document to a folder or moves it back to root (unorganized).
    Pass folder_id=<pk> to move to folder, or folder_id='' to move to root.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_deletable_document_or_404(request.user, pk)
        folder_id = request.POST.get('folder_id', '').strip()

        if folder_id:
            try:
                folder = get_viewable_folder_or_404(request.user, folder_id)
            except Http404:
                return JsonResponse({"success": False, "error": "Folder not found."}, status=404)
            if folder.workspace_id != doc.workspace_id:
                return JsonResponse({"success": False, "error": "Cannot move a document into a different workspace."}, status=400)
            doc.folder = folder
        else:
            doc.folder = None

        doc.save(update_fields=['folder'])
        return JsonResponse({
            "success": True,
            "folder_id": doc.folder_id,
            "folder_name": doc.folder.name if doc.folder else None,
        })

class ManageFoldersView(LoginRequiredMixin, View):
    """
    Renders the dedicated page for managing folders (root folders by default).
    """
    login_url = "/accounts/login/"
    template_name = "documents/manage_folders.html"

    def get(self, request):
        query = request.GET.get('q', '').strip()
        active_workspace = get_active_workspace(request)

        # Base queryset
        folders_qs = visible_folders_for(request.user, active_workspace)

        if query:
            folders_qs = folders_qs.filter(name__icontains=query)
        else:
            # Default: show root folders
            folders_qs = folders_qs.filter(parent__isnull=True)

        folders_qs = list(folders_qs.prefetch_related('documents'))
        for folder in folders_qs:
            folder.can_edit = user_can_edit_folder(request.user, folder)

        all_documents = visible_documents_for(request.user, active_workspace).order_by('-uploaded_at')
        all_folders_list = visible_folders_for(request.user, active_workspace).order_by('name')

        return render(request, self.template_name, {
            "folders": folders_qs,
            "query": query,
            "all_documents": all_documents,
            "all_folders_list": all_folders_list,
            "page_title": "Manage Folders",
            "active_workspace": active_workspace,
        })

class FolderCreateFormView(LoginRequiredMixin, View):
    """
    Renders the full-page form to create a new folder.
    """
    login_url = "/accounts/login/"
    template_name = "documents/folder_form.html"

    def get(self, request):
        parents = visible_folders_for(request.user, get_active_workspace(request))
        folder = Folder(parent_id=request.GET.get('parent_id'))
        return render(request, self.template_name, {
            "parents": parents,
            "folder": folder,
            "page_title": "Create new folder",
        })

    def post(self, request):
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id')
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Folder name is required.")
            return redirect('documents:folder_add_page')

        parent = None
        workspace = get_active_workspace(request)
        if parent_id:
            try:
                parent = get_viewable_folder_or_404(request.user, parent_id)
            except Http404:
                messages.error(request, "Parent folder not found.")
                return redirect('documents:folder_add_page')
            workspace = parent.workspace

        if workspace:
            duplicate_exists = Folder.objects.filter(workspace=workspace, name=name, parent=parent).exists()
        else:
            duplicate_exists = Folder.objects.filter(user=request.user, workspace__isnull=True, name=name, parent=parent).exists()
        if duplicate_exists:
            messages.error(request, "A folder with this name already exists here.")
            return redirect('documents:folder_add_page')

        Folder.objects.create(
            user=request.user,
            workspace=workspace,
            name=name,
            parent=parent,
            description=description,
        )
        messages.success(request, f"Folder '{name}' created successfully.")
        return redirect('documents:folder_manage')

class FolderEditFormView(LoginRequiredMixin, View):
    """
    Renders the full-page form to edit an existing folder.
    """
    login_url = "/accounts/login/"
    template_name = "documents/folder_form.html"

    def get(self, request, pk):
        folder = get_editable_folder_or_404(request.user, pk)
        parents = visible_folders_for(request.user, folder.workspace).exclude(pk=pk)
        return render(request, self.template_name, {
            "folder": folder,
            "parents": parents,
            "page_title": f"Edit Folder: {folder.name}",
        })

    def post(self, request, pk):
        folder = get_editable_folder_or_404(request.user, pk)
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id')
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Folder name is required.")
            return redirect('documents:folder_edit_page', pk=pk)

        parent = None
        if parent_id:
            try:
                parent = get_viewable_folder_or_404(request.user, parent_id)
            except Http404:
                messages.error(request, "Parent folder not found.")
                return redirect('documents:folder_edit_page', pk=pk)

            # Guard against moving into descendants
            if folder.is_ancestor_of(parent):
                messages.error(request, "Cannot move a folder into its own subfolder.")
                return redirect('documents:folder_edit_page', pk=pk)

            # Guard: cannot move a folder across workspace boundaries
            if parent.workspace_id != folder.workspace_id:
                messages.error(request, "Cannot move a folder into a different workspace.")
                return redirect('documents:folder_edit_page', pk=pk)

        # Check unique constraint excluding self — scoped by workspace for shared folders, by user for personal ones
        if folder.workspace:
            duplicate_exists = Folder.objects.filter(workspace=folder.workspace, name=name, parent=parent).exclude(pk=pk).exists()
        else:
            duplicate_exists = Folder.objects.filter(user=request.user, workspace__isnull=True, name=name, parent=parent).exclude(pk=pk).exists()
        if duplicate_exists:
            messages.error(request, "A folder with this name already exists in the target location.")
            return redirect('documents:folder_edit_page', pk=pk)

        folder.name = name
        folder.parent = parent
        folder.description = description
        folder.save()

        messages.success(request, f"Folder '{name}' updated successfully.")
        return redirect('documents:folder_manage')

class AddDocumentsToFolderAjaxView(LoginRequiredMixin, View):
    """
    AJAX endpoint to assign multiple documents to a folder.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        folder = get_editable_folder_or_404(request.user, pk)
        document_ids = request.POST.getlist('document_ids[]')

        if not document_ids:
            return JsonResponse({"success": False, "error": "No documents selected."}, status=400)

        # Only documents the user can move (their own uploads, or any doc if they admin the workspace)
        # may be reassigned, and only within the folder's own workspace.
        if folder.workspace and is_workspace_admin(request.user, folder.workspace):
            docs = Document.objects.filter(workspace=folder.workspace, pk__in=document_ids)
        elif folder.workspace:
            docs = Document.objects.filter(workspace=folder.workspace, user=request.user, pk__in=document_ids)
        else:
            docs = Document.objects.filter(user=request.user, workspace__isnull=True, pk__in=document_ids)
        updated_count = docs.update(folder=folder)
        
        return JsonResponse({
            "success": True,
            "message": f"Added {updated_count} documents to {folder.name}."
        })

class UnassignedDocumentsAjaxView(LoginRequiredMixin, View):
    """
    AJAX endpoint to fetch paginated documents for the Add Document modal.
    """
    def get(self, request):
        page_number = request.GET.get('page', 1)
        exclude_folder = request.GET.get('exclude_folder')
        
        docs = visible_documents_for(request.user, get_active_workspace(request))
        if exclude_folder:
            docs = docs.exclude(folder_id=exclude_folder)
            
        docs = docs.order_by('-uploaded_at')
        paginator = Paginator(docs, 20)
        
        page_obj = paginator.get_page(page_number)
        
        data = [{
            'id': d.pk,
            'title': d.title
        } for d in page_obj.object_list]
        
        return JsonResponse({
            'documents': data,
            'has_next': page_obj.has_next()
        })


class RewriteContentAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to trigger on-demand document rewriting.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_editable_document_or_404(request.user, pk)
        style = request.POST.get('style')
        
        valid_styles = ['Simplified', 'Formal', 'Academic', 'Casual']
        if style not in valid_styles:
            return JsonResponse({"success": False, "error": "Invalid rewrite style."}, status=400)
            
        try:
            # Clear previous result
            doc.rewrite_content = None
            doc.rewrite_style = style
            doc.save()
            
            async_task(
                'documents.tasks.rewrite_content_task',
                doc.id,
                style,
                task_name=f"rewrite_{doc.id}_{style}"
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class RewriteStatusAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to poll for rewrite status.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        from documents.templatetags.markdown_extras import markdown_to_html
        
        doc = get_viewable_document_or_404(request.user, pk)
        content = doc.rewrite_content
            
        if content:
            if content.startswith("Failed to rewrite"):
                return JsonResponse({"success": False, "error": content})
            return JsonResponse({"success": True, "content": markdown_to_html(content)})
        else:
            return JsonResponse({"success": True, "status": "processing"})


class ExtractKeyPointsAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to trigger on-demand key points extraction.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_editable_document_or_404(request.user, pk)

        try:
            # Clear previous result
            doc.key_points = None
            doc.save()
            
            async_task(
                'documents.tasks.extract_key_points_task',
                doc.id,
                task_name=f"extract_key_points_{doc.id}"
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class KeyPointsStatusAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to poll for key points status.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        from documents.templatetags.markdown_extras import markdown_to_html
        
        doc = get_viewable_document_or_404(request.user, pk)
        content = doc.key_points
            
        if content:
            if content.startswith("Failed to extract"):
                return JsonResponse({"success": False, "error": content})
            return JsonResponse({"success": True, "content": markdown_to_html(content)})
        else:
            return JsonResponse({"success": True, "status": "processing"})


class GenerateFAQsAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to trigger on-demand FAQs generation.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_editable_document_or_404(request.user, pk)

        try:
            # Clear previous result
            doc.faqs = None
            doc.save()
            
            async_task(
                'documents.tasks.generate_faqs_task',
                doc.id,
                task_name=f"generate_faqs_{doc.id}"
            )
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class FAQsStatusAjaxView(LoginRequiredMixin, View):
    """
    Handles AJAX requests to poll for FAQs status.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        from documents.templatetags.markdown_extras import markdown_to_html
        
        doc = get_viewable_document_or_404(request.user, pk)
        content = doc.faqs
            
        if content:
            if content.startswith("Failed to generate"):
                return JsonResponse({"success": False, "error": content})
            return JsonResponse({"success": True, "content": markdown_to_html(content)})
        else:
            return JsonResponse({"success": True, "status": "processing"})

class DocumentCompareCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        document_base = get_editable_document_or_404(request.user, pk)
        compare_doc_id = request.POST.get('compare_doc_id')

        if not compare_doc_id:
            messages.error(request, "Please select a document to compare with.")
            return redirect('documents:detail', pk=pk)

        document_compare = get_viewable_document_or_404(request.user, compare_doc_id)
        
        if document_base == document_compare:
            messages.error(request, "Cannot compare a document with itself.")
            return redirect('documents:detail', pk=pk)

        comparison, created = DocumentComparison.objects.get_or_create(
            user=request.user,
            document_base=document_base,
            document_compare=document_compare
        )
        
        comparison.status = 'processing'
        comparison.save()
        async_task('documents.tasks.compare_documents_task', comparison.id)
            
        from django.urls import reverse
        return redirect('documents:comparison_detail', comparison_id=comparison.id)

class ComparisonDetailView(LoginRequiredMixin, View):
    template_name = "documents/document_compare.html"
    
    def get(self, request, comparison_id):
        comparison = get_object_or_404(DocumentComparison, pk=comparison_id, user=request.user)
        return render(request, self.template_name, {'comparison': comparison})

class ComparisonStatusAjaxView(LoginRequiredMixin, View):
    def get(self, request, comparison_id):
        comparison = get_object_or_404(DocumentComparison, pk=comparison_id, user=request.user)
        if comparison.status == 'processing':
            return render(request, 'documents/partials/compare_loading.html', {'comparison': comparison})
        elif comparison.status == 'failed':
            return render(request, 'documents/partials/compare_failed.html', {'comparison': comparison})
        else:
            from django.http import HttpResponse
            response = HttpResponse()
            from django.urls import reverse
            response['HX-Redirect'] = request.build_absolute_uri(reverse('documents:comparison_detail', args=[comparison.id]))
            return response


# ─── Reader & Annotations Views ───────────────────────────────────────────────

class DocumentReaderView(LoginRequiredMixin, View):
    """
    Renders the full-screen PDF reader and annotations sidebar.
    """
    login_url = "/accounts/login/"
    template_name = "documents/reader.html"

    def get(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        return render(request, self.template_name, {
            "document": doc,
            "page_title": f"Reading: {doc.title}"
        })


class AnnotationsAjaxView(LoginRequiredMixin, View):
    """
    Returns all bookmarks, highlights, and notes for a document.
    """
    def get(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        
        bookmarks = list(doc.bookmarks.filter(user=request.user).values(
            'id', 'page_number', 'title', 'created_at'
        ))
        
        highlights = list(doc.highlights.filter(user=request.user).values(
            'id', 'page_number', 'text', 'color', 'position_data', 'created_at', 'updated_at'
        ))
        
        notes = list(doc.notes.filter(user=request.user).values(
            'id', 'page_number', 'content', 'highlight_id', 'created_at', 'updated_at'
        ))

        return JsonResponse({
            "success": True,
            "bookmarks": bookmarks,
            "highlights": highlights,
            "notes": notes
        })


class BookmarksAjaxView(LoginRequiredMixin, View):
    """
    Add or remove a bookmark.
    """
    def post(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        try:
            data = json.loads(request.body)
            action = data.get('action')
            page_number = int(data.get('page_number'))
            
            if action == 'add':
                title = data.get('title', f'Page {page_number}')
                bookmark, created = Bookmark.objects.get_or_create(
                    document=doc, user=request.user, page_number=page_number,
                    defaults={'title': title}
                )
                return JsonResponse({
                    "success": True, 
                    "bookmark": {
                        "id": bookmark.id,
                        "page_number": bookmark.page_number,
                        "title": bookmark.title,
                        "created_at": bookmark.created_at
                    }
                })
            elif action == 'remove':
                Bookmark.objects.filter(document=doc, user=request.user, page_number=page_number).delete()
                return JsonResponse({"success": True})
            return JsonResponse({"success": False, "error": "Invalid action"}, status=400)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)


class HighlightsAjaxView(LoginRequiredMixin, View):
    """
    Add or delete highlights.
    """
    def post(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        try:
            data = json.loads(request.body)
            page_number = int(data.get('page_number'))
            text = data.get('text', '')
            color = data.get('color', 'yellow')
            position_data = data.get('position_data', {})
            
            highlight = Highlight.objects.create(
                document=doc,
                user=request.user,
                page_number=page_number,
                text=text,
                color=color,
                position_data=position_data
            )
            return JsonResponse({
                "success": True,
                "highlight": {
                    "id": highlight.id,
                    "page_number": highlight.page_number,
                    "text": highlight.text,
                    "color": highlight.color,
                    "position_data": highlight.position_data,
                    "created_at": highlight.created_at,
                    "updated_at": highlight.updated_at
                }
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

    def delete(self, request, pk, highlight_id):
        Highlight.objects.filter(id=highlight_id, document_id=pk, user=request.user).delete()
        return JsonResponse({"success": True})


class NotesAjaxView(LoginRequiredMixin, View):
    """
    Add, edit, or delete notes.
    """
    def post(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        try:
            data = json.loads(request.body)
            note_id = data.get('id')
            page_number = int(data.get('page_number'))
            content = data.get('content', '')
            highlight_id = data.get('highlight_id')
            
            if note_id:
                note = get_object_or_404(Note, id=note_id, document=doc, user=request.user)
                note.content = content
                note.save()
            else:
                highlight = Highlight.objects.filter(id=highlight_id, user=request.user).first() if highlight_id else None
                note = Note.objects.create(
                    document=doc,
                    user=request.user,
                    page_number=page_number,
                    content=content,
                    highlight=highlight
                )
            return JsonResponse({
                "success": True,
                "note": {
                    "id": note.id,
                    "page_number": note.page_number,
                    "content": note.content,
                    "highlight_id": note.highlight_id,
                    "created_at": note.created_at,
                    "updated_at": note.updated_at
                }
            })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)

    def delete(self, request, pk, note_id):
        Note.objects.filter(id=note_id, document_id=pk, user=request.user).delete()
        return JsonResponse({"success": True})


class NotesSearchAjaxView(LoginRequiredMixin, View):
    """
    Search notes and highlights.
    """
    def get(self, request, pk):
        doc = get_viewable_document_or_404(request.user, pk)
        q = request.GET.get('q', '').strip()
        
        if not q:
            return JsonResponse({"success": True, "notes": [], "highlights": []})
            
        # Search Notes (and Notes attached to highlights)
        notes_qs = Note.objects.filter(
            Q(content__icontains=q) | Q(highlight__text__icontains=q),
            document=doc, user=request.user
        ).values('id', 'page_number', 'content', 'highlight_id', 'created_at', 'updated_at')
        
        # Search Highlights directly (that might not have a note)
        highlights_qs = Highlight.objects.filter(
            Q(text__icontains=q),
            document=doc, user=request.user
        ).values('id', 'page_number', 'text', 'color', 'position_data', 'created_at', 'updated_at')
        
        return JsonResponse({
            "success": True,
            "notes": list(notes_qs),
            "highlights": list(highlights_qs)
        })
