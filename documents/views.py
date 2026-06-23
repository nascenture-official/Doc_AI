import time
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse, FileResponse
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_protect

from django_q.tasks import async_task

from .models import Document, Folder
from .services.vector_store import delete_vector_index

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

        documents_qs = Document.objects.filter(user=request.user).defer(
            'summary_short', 'summary_long', 'error_message'
        )

        if folder_id:
            try:
                current_folder = Folder.objects.get(pk=folder_id, user=request.user)
                documents_qs = documents_qs.filter(folder=current_folder)
            except Folder.DoesNotExist:
                current_folder = None
        elif 'folder' in request.GET and request.GET['folder'] == '':
            # Explicit empty string → show unorganized docs (folder=NULL)
            documents_qs = documents_qs.filter(folder__isnull=True)

        paginator = Paginator(documents_qs, DOCUMENTS_PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        root_folders = Folder.objects.filter(user=request.user, parent__isnull=True)

        return render(request, self.template_name, {
            "documents": page_obj,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "page_title": "My Documents",
            "root_folders": root_folders,
            "current_folder": current_folder,
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
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        return render(request, "documents/_status_badge.html", {"doc": doc, "is_htmx": True})

class DocumentDetailView(LoginRequiredMixin, View):
    """
    Renders detailed view of a document including its summaries and metadata.
    """
    login_url = "/accounts/login/"
    template_name = "documents/detail.html"

    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        return render(request, self.template_name, {
            "document": doc,
            "page_title": f"Document: {doc.title}",
        })

class DocumentDeleteView(LoginRequiredMixin, View):
    """
    Deletes the document record, deletes its corresponding PDF from storage,
    and removes its corresponding FAISS vector index files from disk.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk, user=request.user)
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
        doc = get_object_or_404(Document, pk=pk, user=request.user)
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
        doc = get_object_or_404(Document, pk=pk, user=request.user)
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
        
        doc = get_object_or_404(Document, pk=pk, user=request.user)
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


# ─── Folder Views ─────────────────────────────────────────────────────────────

class FolderDetailView(LoginRequiredMixin, View):
    """
    Shows all documents directly inside a specific folder, along with its
    direct child subfolders and a breadcrumb for navigation.
    """
    login_url = "/accounts/login/"
    template_name = "documents/folder_detail.html"

    def get(self, request, pk):
        folder = get_object_or_404(Folder, pk=pk, user=request.user)

        documents_qs = Document.objects.filter(
            user=request.user, folder=folder
        ).defer('summary_short', 'summary_long', 'error_message')

        paginator = Paginator(documents_qs, DOCUMENTS_PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        root_folders = Folder.objects.filter(user=request.user, parent__isnull=True)

        return render(request, self.template_name, {
            "folder": folder,
            "documents": page_obj,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "subfolders": folder.children.all(),
            "breadcrumb": folder.get_breadcrumb(),
            "root_folders": root_folders,
            "current_folder": folder,
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
        if parent_id:
            try:
                parent = Folder.objects.get(pk=parent_id, user=request.user)
            except Folder.DoesNotExist:
                return JsonResponse({"success": False, "error": "Parent folder not found."}, status=404)

        # Check unique_together constraint
        if Folder.objects.filter(user=request.user, name=name, parent=parent).exists():
            return JsonResponse({"success": False, "error": "A folder with this name already exists here."}, status=400)

        folder = Folder.objects.create(user=request.user, name=name, parent=parent)
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
        folder = get_object_or_404(Folder, pk=pk, user=request.user)
        name = request.POST.get('name', '').strip()

        if not name:
            return JsonResponse({"success": False, "error": "Folder name cannot be empty."}, status=400)

        # Check uniqueness in the same parent
        qs = Folder.objects.filter(user=request.user, name=name, parent=folder.parent).exclude(pk=pk)
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
        folder = get_object_or_404(Folder, pk=pk, user=request.user)
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
        folder = get_object_or_404(Folder, pk=pk, user=request.user)
        new_parent_id = request.POST.get('new_parent_id', '').strip()

        new_parent = None
        if new_parent_id:
            try:
                new_parent = Folder.objects.get(pk=new_parent_id, user=request.user)
            except Folder.DoesNotExist:
                return JsonResponse({"success": False, "error": "Target folder not found."}, status=404)

            # Guard: cannot move into own descendant
            if folder.pk == new_parent.pk or folder.is_ancestor_of(new_parent):
                return JsonResponse({
                    "success": False,
                    "error": "Cannot move a folder into itself or one of its subfolders."
                }, status=400)

        # Check name uniqueness at new location
        if Folder.objects.filter(user=request.user, name=folder.name, parent=new_parent).exclude(pk=pk).exists():
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
        doc = get_object_or_404(Document, pk=pk, user=request.user)
        folder_id = request.POST.get('folder_id', '').strip()

        if folder_id:
            try:
                folder = Folder.objects.get(pk=folder_id, user=request.user)
            except Folder.DoesNotExist:
                return JsonResponse({"success": False, "error": "Folder not found."}, status=404)
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
        
        # Base queryset
        folders_qs = Folder.objects.filter(user=request.user)
        
        if query:
            folders_qs = folders_qs.filter(name__icontains=query)
        else:
            # Default: show root folders
            folders_qs = folders_qs.filter(parent__isnull=True)
            
        folders_qs = folders_qs.prefetch_related('documents')
        
        all_documents = Document.objects.filter(user=request.user).order_by('-uploaded_at')
        all_folders_list = Folder.objects.filter(user=request.user).order_by('name')

        return render(request, self.template_name, {
            "folders": folders_qs,
            "query": query,
            "all_documents": all_documents,
            "all_folders_list": all_folders_list,
            "page_title": "Manage Folders",
        })

class FolderCreateFormView(LoginRequiredMixin, View):
    """
    Renders the full-page form to create a new folder.
    """
    login_url = "/accounts/login/"
    template_name = "documents/folder_form.html"

    def get(self, request):
        parents = Folder.objects.filter(user=request.user)
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
        if parent_id:
            try:
                parent = Folder.objects.get(pk=parent_id, user=request.user)
            except Folder.DoesNotExist:
                messages.error(request, "Parent folder not found.")
                return redirect('documents:folder_add_page')

        if Folder.objects.filter(user=request.user, name=name, parent=parent).exists():
            messages.error(request, "A folder with this name already exists here.")
            return redirect('documents:folder_add_page')

        Folder.objects.create(
            user=request.user,
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
        folder = get_object_or_404(Folder, pk=pk, user=request.user)
        parents = Folder.objects.filter(user=request.user).exclude(pk=pk)
        return render(request, self.template_name, {
            "folder": folder,
            "parents": parents,
            "page_title": f"Edit Folder: {folder.name}",
        })

    def post(self, request, pk):
        folder = get_object_or_404(Folder, pk=pk, user=request.user)
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id')
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, "Folder name is required.")
            return redirect('documents:folder_edit_page', pk=pk)

        parent = None
        if parent_id:
            try:
                parent = Folder.objects.get(pk=parent_id, user=request.user)
            except Folder.DoesNotExist:
                messages.error(request, "Parent folder not found.")
                return redirect('documents:folder_edit_page', pk=pk)
            
            # Guard against moving into descendants
            if folder.is_ancestor_of(parent):
                messages.error(request, "Cannot move a folder into its own subfolder.")
                return redirect('documents:folder_edit_page', pk=pk)

        # Check unique constraint excluding self
        if Folder.objects.filter(user=request.user, name=name, parent=parent).exclude(pk=pk).exists():
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
        folder = get_object_or_404(Folder, pk=pk, user=request.user)
        document_ids = request.POST.getlist('document_ids[]')
        
        if not document_ids:
            return JsonResponse({"success": False, "error": "No documents selected."}, status=400)
            
        docs = Document.objects.filter(user=request.user, pk__in=document_ids)
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
        
        docs = Document.objects.filter(user=request.user)
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
