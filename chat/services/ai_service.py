import json
import logging
from django.conf import settings
from django.core.cache import cache
from django.template.loader import render_to_string
from documents.services.vector_store import get_vector_store
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


def generate_chat_response(conversation, user_message_text):
    """
    Smart RAG pipeline utilizing LangChain and OpenAI:
    0. Classifies the message — if conversational small-talk, responds directly
       with NO vector search and NO citations.
    1. (Document questions only) Loads merged FAISS vector store.
    2. Performs similarity search to retrieve contextual excerpts.
    3. Formulates a system prompt forcing strict document-only grounding.
    4. Invokes ChatOpenAI (gpt-4o-mini) to generate answers.
    5. Returns (answer_text, sources_list).
    """
    documents = conversation.documents.all()
    if not documents.exists():
        return "Please connect at least one document to this chat to start asking questions.", []

    api_key = getattr(settings, 'OPENAI_API_KEY', None)

    # ── Step 0: Intent classification ──────────────────────────────────────
    if _is_conversational(user_message_text, api_key):
        # Pure small-talk — skip RAG entirely, return empty sources
        answer_text = _direct_chat_response(user_message_text, conversation, api_key)
        return answer_text, []

    # ── Step 1: Load vector store ───────────────────────────────────────────
    doc_ids = [str(doc.id) for doc in documents]
    try:
        db = get_vector_store()
    except Exception as e:
        logger.error(f"Failed to load vector index for chat: {str(e)}")
        return "Failed to load document indices. Please make sure the documents are processed successfully.", []

    if not db:
        return "No text contents found. Please wait for the documents to finish processing.", []

    # Retrieve top 5 matching passages, filtering out low-relevance chunks
    # FAISS uses L2 distance — lower score = more similar. Threshold 1.0 keeps only relevant results.
    # Chroma uses Cosine distance or L2 by default, where lower is also better.
    retrieved_docs = db.similarity_search(
        query= user_message_text, k=5,filter={"document_id": {"$in": doc_ids}}
    )

    print("retrieved_docs====", retrieved_docs)

    # ── Step 2: Compile context ─────────────────────────────────────────────
    context = "\n\n".join([doc.page_content for doc in retrieved_docs])

    # ── Step 4: System prompt ───────────────────────────────────────────────
    system_prompt = ("""
        You are an AI assistant that answers questions using ONLY the provided document context.

        Rules:
        1. Use only the information found in the Context section.
        2. Do not use your own knowledge or make assumptions.
        3. If the Context does not contain enough information to answer the Question, do not invent an answer.
        4. If the Context appears unrelated to the Question, clearly state that the documents do not contain relevant information.

        Context:
        {context}

        Question:
        {question}
        """).format(
            context=context, question=user_message_text)

    # ── Step 5: Invoke ChatOpenAI ───────────────────────────────────────────
    try:
        llm = ChatOpenAI(
            model="gpt-5-mini",
            api_key=api_key,
            temperature=0.5
        )
        response = llm.invoke(system_prompt)
        answer_text = response.content.strip()
    except Exception as e:
        logger.error(f"Error calling ChatOpenAI: {str(e)}")
        return f"Error communicating with OpenAI: {str(e)}", []

    # ── Step 6: Build citations list ────────────────────────────────────────
    sources = []
    seen = set()
    for doc in retrieved_docs:
        source_name = doc.metadata.get("source", "Unknown")
        page_num = doc.metadata.get("page_label", 1)
        print("page_num==",page_num)
        key = (source_name, page_num)
        if key not in seen:
            seen.add(key)
            sources.append({
                "source": source_name,
                "page": page_num,
                "excerpt": doc.page_content[:100] + "..."
            })

    return answer_text, sources

def stream_chat_response(conversation, user_message_text, user_msg_id):
    """Generator yielding SSE-formatted strings for streaming LLM responses."""
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
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
                "Do NOT reference any documents or citations.\n\n"
                f"CONVERSATION HISTORY:\n{history_str}\nUser: {user_message_text}\nAssistant:"
            )
            llm_stream = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.7).stream(system_prompt)

        else:
            try:
                db = get_vector_store()
            except Exception as e:
                logger.error(f"Vector store error during stream: {e}")
                yield f'data: {json.dumps({"type": "error", "message": "Failed to load document index."})}\n\n'
                return

            if not db:
                yield f'data: {json.dumps({"type": "error", "message": "No document index found."})}\n\n'
                return

            doc_ids = [str(doc.id) for doc in documents]
            retrieved_docs = db.similarity_search(
                query=user_message_text, k=5,
                filter={"document_id": {"$in": doc_ids}}
            )
            context = "\n\n".join(d.page_content for d in retrieved_docs)

            seen = set()
            for doc in retrieved_docs:
                src = doc.metadata.get("source", "Unknown")
                pg = doc.metadata.get("page_label", 1)
                key = (src, pg)
                if key not in seen:
                    seen.add(key)
                    sources.append({"source": src, "page": pg, "excerpt": doc.page_content[:100] + "..."})

            recent_msgs = Message.objects.filter(conversation=conversation).order_by('-created_at')[1:5]
            history_str = "".join(
                f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}\n"
                for m in reversed(list(recent_msgs))
            )
            system_prompt = (
                "You are an AI assistant that answers questions using the provided document context.\n\n"
                "Rules:\n"
                "1. Use only the information found in the Context section.\n"
                "2. Do not use your own knowledge or make assumptions.\n"
                "4. Only say you cannot answer if the context contains absolutely no relevant information.\n\n"
                + (f"Recent conversation:\n{history_str}\n" if history_str.strip() else "")
                + f"Context:\n{context}\n\nQuestion:\n{user_message_text}"
            )
            llm_stream = ChatOpenAI(model="gpt-5-mini", api_key=api_key, temperature=0.5).stream(system_prompt)

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

