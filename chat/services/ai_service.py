import json
import logging
from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string
from documents.services.vector_store import get_hybrid_retriever
from langchain_openai import ChatOpenAI
from chat.models import Message

logger = logging.getLogger(__name__)


def _is_conversational(user_message_text, api_key):
    """
    Uses the LLM to decide whether the user's message is casual small-talk
    (greetings, thanks, chit-chat) or a genuine document question.

    Returns True  → conversational / no RAG needed
    Returns False → document question / run full RAG pipeline
    """
    classification_prompt = (
        "You are a message classifier. Your only job is to decide whether the "
        "following user message is:\n"
        "  A) Conversational small-talk (greetings, thanks, how-are-you, jokes, "
        "general chit-chat, anything NOT asking about a document)\n"
        "  B) A question or request that requires searching a document\n\n"
        "Reply with exactly one word: SMALLTALK or DOCUMENT.\n\n"
        f"User message: \"{user_message_text}\""
    )
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.0)
        result = llm.invoke(classification_prompt).content.strip().upper()
        return result == "SMALLTALK"
    except Exception as e:
        logger.warning(f"Intent classification failed, defaulting to DOCUMENT: {e}")
        return False  # safe default: run RAG


def _split_into_questions(user_message_text, api_key):
    """
    Splits a multi-question message into individual questions so each gets
    its own retrieval pass. Returns a list with the original text unchanged
    if splitting fails or yields nothing useful.
    """
    prompt = (
        "Split the following user message into a list of individual questions or requests. "
        "Return ONLY a valid JSON array of strings, one element per question. "
        "If the message is already a single question, return a JSON array containing just that one string. "
        "Do NOT add explanations or markdown code fences.\n\n"
        f"User message: \"{user_message_text}\""
    )
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.0)
        raw = llm.invoke(prompt).content.strip()
        # Strip markdown code fences if the model wraps the output
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        questions = json.loads(raw)
        if isinstance(questions, list):
            cleaned = [q.strip() for q in questions if isinstance(q, str) and q.strip()]
            if cleaned:
                return cleaned
    except Exception as e:
        logger.warning(f"Question splitting failed, using original message: {e}")
    return [user_message_text]


def _direct_chat_response(user_message_text, conversation, api_key):
    """
    Returns a friendly conversational reply without touching the vector store.
    """
    last_messages = Message.objects.filter(conversation=conversation).order_by('-created_at')[1:7]
    last_messages = list(reversed(last_messages))
    history_str = ""
    for msg in last_messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_str += f"{role_label}: {msg.content}\n"

    system_prompt = (
        "You are a helpful and friendly document assistant. "
        "The user has sent a conversational message — respond warmly and naturally. "
        "Do NOT reference any documents or citations.\n\n"
        f"CONVERSATION HISTORY:\n{history_str}\n"
        f"User: {user_message_text}\n"
        "Assistant:"
    )
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.7)
        return llm.invoke(system_prompt).content.strip()
    except Exception as e:
        logger.error(f"Error in direct chat response: {e}")
        return "Hello! How can I help you with your documents today?"


def stream_chat_response(conversation, user_message_text, user_msg_id, new_title=None):
    """Generator yielding SSE-formatted strings for streaming LLM responses."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None)

    # Emit title event immediately so the client can update the sidebar without a refresh
    if new_title:
        yield f'data: {json.dumps({"type": "title", "title": new_title, "convo_id": conversation.id})}\n\n'
    documents = conversation.documents.all()

    try:
        if not documents.exists():
            yield f'data: {json.dumps({"type": "error", "message": "No documents connected."})}\n\n'
            return

        # Intent classification (blocking, before first token)
        is_smalltalk = _is_conversational(user_message_text, api_key)

        if cache.get(f'abort_msg_{user_msg_id}'):
            cache.delete(f'abort_msg_{user_msg_id}')
            yield f'data: {json.dumps({"type": "abort"})}\n\n'
            return

        sources = []
        if is_smalltalk:
            last_messages = Message.objects.filter(conversation=conversation).order_by('-created_at')[1:7]
            history_str = "".join(
                f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}\n"
                for m in reversed(list(last_messages))
            )
            system_prompt = (
                "You are a helpful and friendly document assistant. "
                "The user has sent a conversational message — respond warmly and naturally. "
                f"User: {user_message_text}\nAssistant:"
            )
            llm_stream = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.7).stream(system_prompt)

        else:
            doc_ids = [str(doc.id) for doc in documents]

            # Base hybrid retriever — alpha=0.7 favors semantic search with BM25 keyword boost
            try:
                base_retriever = get_hybrid_retriever(document_ids=doc_ids, k=10, alpha=0.7)
            except Exception as e:
                logger.error(f"Hybrid retriever error during stream: {e}")
                yield f'data: {json.dumps({"type": "error", "message": "Failed to load document index."})}\n\n'
                return

            # Split multi-question messages so each question gets its own retrieval pass.
            # This ensures "phase 1" in a LangGraph PDF isn't drowned out by "attention"
            # from a different PDF when both are asked together.
            questions = _split_into_questions(user_message_text, api_key)
            logger.info(f"Detected {len(questions)} question(s): {questions}")

            # Retrieve candidates per question, deduplicating by content prefix
            all_candidate_docs = []
            seen_texts = set()
            for question in questions:
                q_docs = base_retriever.invoke(question)
                for doc in q_docs:
                    dedup_key = doc.page_content[:200]
                    if dedup_key not in seen_texts:
                        seen_texts.add(dedup_key)
                        all_candidate_docs.append(doc)

            # Round-robin diversity — 5 chunks per question, capped at 20 total
            chunk_cap = min(5 * len(questions), 20)
            diverse_docs = []
            docs_by_id = {}
            for doc in all_candidate_docs:
                doc_id = doc.metadata.get("document_id")
                if doc_id not in docs_by_id:
                    docs_by_id[doc_id] = []
                docs_by_id[doc_id].append(doc)

            while len(diverse_docs) < chunk_cap and docs_by_id:
                to_remove = []
                for doc_id, docs in docs_by_id.items():
                    if len(diverse_docs) >= chunk_cap:
                        break
                    diverse_docs.append(docs.pop(0))
                    if not docs:
                        to_remove.append(doc_id)
                for doc_id in to_remove:
                    del docs_by_id[doc_id]

            retrieved_docs = diverse_docs
            context = "\n\n".join(d.page_content for d in retrieved_docs)

            seen = set()
            for doc in retrieved_docs:
                src = doc.metadata.get("title") or doc.metadata.get("source", "Unknown")
                pg = doc.metadata.get("page_label", 1)
                key = (src, pg)
                if key not in seen:
                    seen.add(key)
                    sources.append({"source": src, "page": pg, "excerpt": doc.page_content[:100] + "..."})

            sources = sources[:20]

            recent_msgs = Message.objects.filter(conversation=conversation).order_by('-created_at')[1:5]
            history_str = "".join(
                f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}\n"
                for m in reversed(list(recent_msgs))
            )


            system_prompt = (
                "You are an AI assistant that answers questions strictly using the provided document context.\n\n"
                "Rules:\n"
                "- Use ONLY the information found in the Context section below.\n"
                "- Do NOT use your own knowledge or make assumptions.\n"
                "- Do NOT mention sources or citations in your answer.\n"
                "- Keep answers short and clear.\n"
                "- If the context does not contain enough information for a question, say so honestly.\n\n"
                f"Context:\n{context}\n\nQuestion(s):\n{user_message_text}"
            )
            llm_stream = ChatOpenAI(model="gpt-5-mini", api_key=api_key, temperature=0.3).stream(system_prompt)

        # Stream tokens
        full_text = ""
        token_count = 0
        for chunk in llm_stream:
            text = chunk.content
            if text:
                full_text += text
                yield f'data: {json.dumps({"type": "token", "text": text})}\n\n'
                token_count += 1
                if token_count % 5 == 0 and cache.get(f'abort_msg_{user_msg_id}'):
                    cache.delete(f'abort_msg_{user_msg_id}')
                    yield f'data: {json.dumps({"type": "abort"})}\n\n'
                    return

        if cache.get(f'abort_msg_{user_msg_id}'):
            cache.delete(f'abort_msg_{user_msg_id}')
            yield f'data: {json.dumps({"type": "abort"})}\n\n'
            return

        assistant_msg = Message.objects.create(
            conversation=conversation,
            role='assistant',
            content=full_text,
            sources=sources
        )
        conversation.save()

        html = render_to_string('chat/_assistant_message.html', {'assistant_msg': assistant_msg})
        yield f'data: {json.dumps({"type": "done", "html": html, "msg_id": assistant_msg.id})}\n\n'

    except Exception as e:
        logger.error(f"stream_chat_response error: {e}")
        yield f'data: {json.dumps({"type": "error", "message": "An error occurred. Please try again."})}\n\n'


def auto_generate_title(first_message_text):
    """
    Generates a brief 3-4 word title for a new conversation based on the first user message.
    """
    prompt = (
        "You are an assistant. Please read the following user question and generate "
        "a very brief title (maximum 4 words) summarizing it. Return only the plain title text, "
        "without quotation marks, prefixes, or punctuation:\n\n"
        f"{first_message_text}"
    )
    try:
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.5
        )
        response = llm.invoke(prompt)
        return response.content.strip()
    except Exception as e:
        logger.warning(f"Failed to auto-generate conversation title: {str(e)}")
        return "New Conversation"
