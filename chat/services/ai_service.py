import logging
from django.conf import settings
from documents.services.vector_store import load_multiple_indexes
from langchain_openai import ChatOpenAI
from chat.models import Message

logger = logging.getLogger(__name__)

def generate_chat_response(conversation, user_message_text):
    """
    RAG-pipeline utilizing LangChain and OpenAI:
    1. Loads merged FAISS vector store for all documents in the conversation.
    2. Performs similarity search to retrieve contextual excerpts.
    3. Formulates a system prompt forcing strict document-only grounding.
    4. Invokes ChatOpenAI (gpt-4o-mini) to generate answers.
    5. Returns (answer_text, sources_list).
    """
    documents = conversation.documents.all()
    if not documents.exists():
        return "Please connect at least one document to this chat to start asking questions.", []

    doc_ids = [doc.id for doc in documents]
    
    # Step 1: Retrieve matching chunks from vector store
    try:
        db = load_multiple_indexes(doc_ids)
    except Exception as e:
        logger.error(f"Failed to load vector indexes for chat: {str(e)}")
        return "Failed to load document indices. Please make sure the documents are processed successfully.", []

    if not db:
        return "No text contents found. Please wait for the documents to finish processing.", []

    # Retrieve top 5 matching passages, filtering out low-relevance chunks
    # FAISS uses L2 distance — lower score = more similar. Threshold 1.0 keeps only relevant results.
    raw_results = db.similarity_search_with_score(user_message_text, k=5)
    retrieved_docs = [doc for doc, score in raw_results if score < 1.0]

    # Fallback: if threshold filtered everything out, use all k=5 results
    if not retrieved_docs:
        retrieved_docs = [doc for doc, score in raw_results]

    # Step 2: Compile context formatting
    context_str = ""
    for idx, doc in enumerate(retrieved_docs):
        source_name = doc.metadata.get("source", "Unknown")
        page_num = doc.metadata.get("page", "?")
        context_str += f"[{idx+1}] File: {source_name} | Page: {page_num}\nContent: {doc.page_content}\n\n"

    # Step 3: Fetch last 5 messages for dialogue history
    # Skip index 0 (the current user message just saved) to avoid duplication in prompt
    last_messages = Message.objects.filter(conversation=conversation).order_by('-created_at')[1:7]
    last_messages = list(reversed(last_messages))  # chronological order
    
    history_str = ""
    for msg in last_messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        history_str += f"{role_label}: {msg.content}\n"

    # Step 4: System Prompt with grounding guidelines
    system_prompt = (
        "You are a helpful and polite document-grounded QA assistant. "
        "Strictly adhere to the following rules:\n"
        "1. If the user greets you or makes conversational small talk (e.g., 'hi', 'how are you', 'thanks'), respond politely and conversationally without referencing documents.\n"
        "2. For factual questions, answer based ONLY on the document excerpts provided below.\n"
        "3. If a factual question cannot be answered using the provided excerpts, state clearly and politely: "
        "'I cannot find this information in the uploaded documents.' and do not speculate.\n"
        "4. Do NOT include citations, document names, or page numbers in your response text (e.g., do not write 'According to DocName' or 'This information is derived from...'). The system will handle citations automatically.\n\n"
        f"CONTEXT EXCERPTS:\n{context_str}\n"
        f"CONVERSATION HISTORY:\n{history_str}\n"
        f"USER QUESTION: {user_message_text}\n"
        "ASSISTANT RESPONSE:"
    )

    # Step 5: Invoke ChatOpenAI
    try:
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.0  # Greedy decoding for maximum reliability
        )
        response = llm.invoke(system_prompt)
        answer_text = response.content.strip()
    except Exception as e:
        logger.error(f"Error calling ChatOpenAI: {str(e)}")
        return f"Error communicating with OpenAI: {str(e)}", []

    # Step 6: Parse source list to save citations
    sources = []
    seen = set()
    for doc in retrieved_docs:
        source_name = doc.metadata.get("source", "Unknown")
        page_num = doc.metadata.get("page", 1)
        key = (source_name, page_num)
        if key not in seen:
            seen.add(key)
            sources.append({
                "source": source_name,
                "page": page_num,
                "excerpt": doc.page_content[:180] + "..."
            })

    return answer_text, sources

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

