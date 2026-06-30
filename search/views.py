from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.core.paginator import Paginator
from documents.models import Document
from documents.services.vector_store import keyword_search_in_vectors, phrase_search_in_vectors
from teams.utils import get_active_workspace
from teams.permissions import visible_documents_for

SEARCH_PAGE_SIZE = 10


class SearchView(LoginRequiredMixin, View):
    """
    Keyword and phrase search across all processed documents — no LLM calls.
    Supports two modes via ?type=keyword (default) and ?type=phrase.
    """
    login_url = "/accounts/login/"
    template_name = "search/search.html"

    def get(self, request):
        query = request.GET.get('q', '').strip()
        search_type = request.GET.get('type', 'keyword')
        if search_type not in ('keyword', 'phrase'):
            search_type = 'keyword'

        all_results = []
        ready_docs = visible_documents_for(request.user, get_active_workspace(request)).filter(status='ready')

        if query and ready_docs.exists():
            doc_ids = list(ready_docs.values_list('id', flat=True))
            if search_type == 'phrase':
                all_results = phrase_search_in_vectors(query, document_ids=doc_ids)
            else:
                all_results = keyword_search_in_vectors(query, document_ids=doc_ids)

        total_count = len(all_results)
        paginator = Paginator(all_results, SEARCH_PAGE_SIZE)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        return render(request, self.template_name, {
            "query": query,
            "search_type": search_type,
            "results": page_obj,
            "page_obj": page_obj,
            "total_count": total_count,
            "page_title": "Search Documents",
        })
