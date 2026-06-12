import time
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse, FileResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from django_q.tasks import async_task

from .models import Document
from .services.pdf_helper import get_pdf_page_count
from .services.vector_store import delete_faiss_index

DOCUMENTS_PAGE_SIZE = 12


class DocumentListView(LoginRequiredMixin, View):
    """
    Renders the page listing all documents owned by the current user.
    Paginates 12 documents per page. Defers heavy fields (summaries)
    not needed on the list view.
    """
    login_url = "/accounts/login/"
    template_name = "documents/list.html"

    def get(self, request):
        documents_qs = Document.objects.filter(user=request.user).defer(
            'summary_short', 'summary_long', 'error_message'
        )
        paginator = Paginator(documents_qs, DOCUMENTS_PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        return render(request, self.template_name, {
            "documents": page_obj,
            "page_obj": page_obj,
            "total_count": paginator.count,
            "page_title": "My Documents",
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
        max_size = 20 * 1024 * 1024  # 20MB
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

        try:
            # First read the page count synchronously using quick pypdf helper
            pages = get_pdf_page_count(doc.file.path)
            if pages > 0:
                doc.page_count = pages
                doc.save()
            else:
                doc.status = 'failed'
                doc.error_message = "Invalid or corrupted PDF file."
                doc.save()
                return JsonResponse({
                    "success": False,
                    "error": doc.error_message,
                    "id": doc.id,
                    "status": doc.status
                }, status=422)
        except Exception as e:
            doc.status = 'failed'
            doc.error_message = f"Failed to parse page count: {str(e)}"
            doc.save()
            return JsonResponse({
                "success": False,
                "error": doc.error_message,
                "id": doc.id,
                "status": doc.status
            }, status=422)

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
            # Delete FAISS vector files from disk
            delete_faiss_index(doc.id)
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
