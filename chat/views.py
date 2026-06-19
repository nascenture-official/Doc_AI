import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.contrib import messages
from django.urls import reverse
from django.core.cache import cache

from documents.models import Document
from .models import Conversation, Message
from .services.ai_service import auto_generate_title, stream_chat_response


# How many messages to load on initial chat page render
MESSAGES_PAGE_SIZE = 30
# How many older messages to load per "load more" batch
MESSAGES_BATCH_SIZE = 20
# How many conversations to show in sidebar before infinite-scroll kicks in
SIDEBAR_PAGE_SIZE = 15


class ChatHomeView(LoginRequiredMixin, View):
    """
    Renders the chat home page. Redirects to the most recent conversation if it exists,
    otherwise redirects to the "new conversation" selection view.
    """
    login_url = "/accounts/login/"

    def get(self, request):
        recent_chat = Conversation.objects.filter(user=request.user).order_by('-updated_at').first()
        if recent_chat:
            return redirect(reverse('chat:detail', args=[recent_chat.id]))
        return redirect(reverse('chat:new'))


class NewConversationView(LoginRequiredMixin, View):
    """
    Renders document selection form to initiate a new conversation.
    """
    login_url = "/accounts/login/"
    template_name = "chat/new.html"

    def get(self, request):
        # Paginate ready docs — 10 per page
        from django.core.paginator import Paginator
        ready_docs_qs = Document.objects.filter(
            user=request.user, status='ready'
        ).only('id', 'title', 'page_count', 'file_size', 'uploaded_at')

        paginator = Paginator(ready_docs_qs, 10)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # Sidebar: first 15 conversations
        conversations = list(
            Conversation.objects.filter(user=request.user)
            .only('id', 'title', 'updated_at')[:SIDEBAR_PAGE_SIZE]
        )
        has_more_conversations = (
            Conversation.objects.filter(user=request.user).count() > SIDEBAR_PAGE_SIZE
        )

        preselected_id = request.GET.get('doc')
        if preselected_id:
            try:
                preselected_id = int(preselected_id)
            except ValueError:
                preselected_id = None

        return render(request, self.template_name, {
            "documents": page_obj,
            "page_obj": page_obj,
            "conversations": conversations,
            "has_more_conversations": has_more_conversations,
            "preselected_id": preselected_id,
            "page_title": "Start New Chat",
        })

    def post(self, request):
        doc_ids = request.POST.getlist('documents')
        if not doc_ids:
            messages.error(request, "You must select at least one document to start a chat.")
            return redirect(reverse('chat:new'))

        convo = Conversation.objects.create(user=request.user, title="New Conversation")
        selected_docs = Document.objects.filter(id__in=doc_ids, user=request.user)
        convo.documents.set(selected_docs)
        convo.save()

        return redirect(reverse('chat:detail', args=[convo.id]))


class ChatDetailView(LoginRequiredMixin, View):
    """
    Renders full conversation interface. Loads only the last MESSAGES_PAGE_SIZE
    messages on initial render — older ones are fetched on-demand via MessageHistoryView.
    """
    login_url = "/accounts/login/"
    template_name = "chat/detail.html"

    def get(self, request, pk):
        convo = get_object_or_404(Conversation, pk=pk, user=request.user)

        # Sidebar: first 15 conversations (optimised fields only)
        conversations = list(
            Conversation.objects.filter(user=request.user)
            .only('id', 'title', 'updated_at')[:SIDEBAR_PAGE_SIZE]
        )
        has_more_conversations = (
            Conversation.objects.filter(user=request.user).count() > SIDEBAR_PAGE_SIZE
        )

        # Messages: load the last MESSAGES_PAGE_SIZE messages only
        all_messages = list(convo.messages.order_by('created_at'))
        total_count = len(all_messages)
        has_older = total_count > MESSAGES_PAGE_SIZE
        messages_list = all_messages[-MESSAGES_PAGE_SIZE:]

        oldest_id = messages_list[0].id if (has_older and messages_list) else None

        return render(request, self.template_name, {
            "conversation": convo,
            "conversations": conversations,
            "has_more_conversations": has_more_conversations,
            "chat_messages": messages_list,
            "has_older": has_older,
            "oldest_id": oldest_id,
            "active_convo_id": convo.id,
            "page_title": convo.title or "Chat",
        })


class MessageHistoryView(LoginRequiredMixin, View):
    """
    HTMX endpoint — returns a batch of older messages that appear before `before_id`.
    Used by the infinite-scroll sentinel at the top of the chat messages area.
    GET /chat/<pk>/messages/?before=<message_id>
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        convo = get_object_or_404(Conversation, pk=pk, user=request.user)
        before_id = request.GET.get('before')

        qs = convo.messages.order_by('-created_at')
        if before_id:
            try:
                qs = qs.filter(id__lt=int(before_id))
            except (ValueError, TypeError):
                pass

        # Fetch one extra to detect if there are even more messages beyond this batch
        batch = list(qs[:MESSAGES_BATCH_SIZE + 1])
        has_more = len(batch) > MESSAGES_BATCH_SIZE
        messages_list = list(reversed(batch[:MESSAGES_BATCH_SIZE]))

        oldest_id = messages_list[0].id if (has_more and messages_list) else None

        return render(request, 'chat/_older_messages.html', {
            'messages': messages_list,
            'has_more': has_more,
            'oldest_id': oldest_id,
            'conversation': convo,
        })


class SidebarConversationsView(LoginRequiredMixin, View):
    """
    HTMX endpoint — returns the next batch of sidebar conversations for infinite scroll.
    GET /chat/sidebar/?offset=<n>&active=<convo_id>
    """
    login_url = "/accounts/login/"

    def get(self, request):
        try:
            offset = int(request.GET.get('offset', 0))
        except (ValueError, TypeError):
            offset = 0

        active_id = request.GET.get('active')
        try:
            active_id = int(active_id) if active_id else None
        except (ValueError, TypeError):
            active_id = None

        # Fetch one extra to detect if more pages exist
        conversations = list(
            Conversation.objects.filter(user=request.user)
            .only('id', 'title', 'updated_at')[offset:offset + SIDEBAR_PAGE_SIZE + 1]
        )
        has_more = len(conversations) > SIDEBAR_PAGE_SIZE
        conversations = conversations[:SIDEBAR_PAGE_SIZE]

        return render(request, 'chat/_sidebar_conversations.html', {
            'conversations': conversations,
            'has_more': has_more,
            'next_offset': offset + SIDEBAR_PAGE_SIZE,
            'active_convo_id': active_id,
        })


class SendMessageView(LoginRequiredMixin, View):
    """
    Phase 1: Instantly saves the user message and returns the user bubble
    plus a loading AI placeholder. The placeholder auto-triggers a GET
    request to GenerateAIResponseView via hx-trigger="load".
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        convo = get_object_or_404(Conversation, pk=pk, user=request.user)
        user_content = request.POST.get('content', '').strip()

        if not user_content:
            return HttpResponse(status=400)

        # Save user message immediately
        user_msg = Message.objects.create(
            conversation=convo,
            role='user',
            content=user_content
        )

        # Return user bubble + pending AI placeholder with a spinner
        response = render(request, 'chat/_user_message.html', {
            'user_msg': user_msg,
            'stream_url': reverse('chat:stream_response', args=[convo.id, user_msg.id]),
        })
        response['HX-Trigger'] = 'clearInput'
        return response


class StreamAIResponseView(LoginRequiredMixin, View):
    """
    Streams the AI response as Server-Sent Events. The client uses fetch() +
    ReadableStream to progressively display tokens, replacing the placeholder
    with server-rendered markdown HTML on completion.
    """
    login_url = "/accounts/login/"

    def get(self, request, pk, user_msg_id):
        convo = get_object_or_404(Conversation, pk=pk, user=request.user)
        user_msg = get_object_or_404(Message, pk=user_msg_id, conversation=convo, role='user')

        # Auto-generate title on first user message and capture it for the stream
        new_title = None
        if convo.messages.filter(role='user').count() == 1:
            new_title = auto_generate_title(user_msg.content)
            convo.title = new_title
            convo.save()

        def event_stream():
            yield from stream_chat_response(convo, user_msg.content, user_msg.id, new_title=new_title)

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response


class AbortGenerationView(LoginRequiredMixin, View):
    """
    Called via AJAX when the user clicks the Stop icon.
    Sets a cache flag that GenerateAIResponseView will check when it finishes.
    """
    def post(self, request, pk, user_msg_id):
        # Set cache key to signal GenerateAIResponseView to drop the response
        cache.set(f"abort_msg_{user_msg_id}", True, timeout=300)
        return HttpResponse(status=204)





class DeleteConversationView(LoginRequiredMixin, View):
    """
    Deletes a conversation. If deleting the currently active conversation,
    responds with HX-Redirect to navigate away.
    """
    login_url = "/accounts/login/"

    def post(self, request, pk):
        convo = get_object_or_404(Conversation, pk=pk, user=request.user)
        active_id = request.POST.get('active_id', '')
        is_active = str(pk) == str(active_id)
        convo.delete()

        if request.headers.get('HX-Request'):
            if is_active:
                # Redirect browser away from the deleted conversation
                response = HttpResponse("")
                response['HX-Redirect'] = reverse('chat:new')
                return response
            # Just remove the sidebar item silently
            return HttpResponse("")

        messages.success(request, "Conversation deleted.")
        return redirect(reverse('chat:new'))


class ConversationMessagesJsonView(LoginRequiredMixin, View):
    """
    Lightweight JSON endpoint used exclusively by the client-side export feature.
    Returns all messages for a conversation as JSON — ownership enforced so users
    can only export their own conversations.
    GET /chat/<pk>/messages-json/
    """
    login_url = "/accounts/login/"

    def get(self, request, pk):
        convo = get_object_or_404(Conversation, pk=pk, user=request.user)
        msgs = list(
            convo.messages.order_by('created_at')
            .values('role', 'content', 'sources', 'created_at')
        )
        # Serialize datetimes to ISO strings (not JSON-serializable by default)
        for m in msgs:
            m['created_at'] = m['created_at'].isoformat()
            # Ensure sources is always a list (never None)
            m['sources'] = m['sources'] or []
        return JsonResponse({'messages': msgs, 'title': convo.title or 'Chat'})
