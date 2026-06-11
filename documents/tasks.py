import logging
from django.utils import timezone
from django.conf import settings
from documents.models import Document
from documents.services.pdf_processor import extract_and_chunk_pdf
from documents.services.vector_store import create_faiss_index
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

def process_uploaded_document(document_id):
    """
    Background worker task to process an uploaded document:
    1. Extracts and chunks text using PyMuPDF/pymupdf4llm & LangChain.
    2. Builds and saves a local FAISS vector store.
    3. Generates short and detailed summaries using OpenAI.
    4. Updates document status to 'ready' (or 'failed' if error).
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist.")
        return

    doc.status = 'processing'
    doc.save()

    try:
        # Step 1: Extract and chunk PDF content
        logger.info(f"Extracting and chunking document '{doc.title}'...")
        langchain_chunks = extract_and_chunk_pdf(doc.file.path, doc.title)
        
        # Step 2: Build FAISS index (saves text + vectors locally on disk)
        logger.info(f"Creating FAISS index for document '{doc.title}'...")
        create_faiss_index(doc.id, langchain_chunks)
        
        # Step 3: Generate summaries using LangChain ChatOpenAI
        logger.info(f"Generating summaries for document '{doc.title}'...")
        
        # Compile content for summarization (limit to prevent token limits)
        full_text = "\n\n".join([chunk.page_content for chunk in langchain_chunks])
        max_chars = 100000  # ~25k tokens
        text_for_summary = full_text[:max_chars]
        
        # Setup OpenAI LLM client
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )
        
        # Short Summary
        try:
            short_summary_resp = llm.invoke([
                SystemMessage(content="You are a professional document analysis assistant."),
                HumanMessage(content=(
                    "Please read the following text extracted from a PDF and generate a concise summary "
                    "in 3-4 bullet points (maximum 120 words). Focus only on key takeaways:\n\n"
                    f"{text_for_summary}"
                ))
            ])
            doc.summary_short = short_summary_resp.content.strip()
        except Exception as se:
            logger.error(f"Failed to generate short summary for document {doc.id}: {str(se)}")
            doc.summary_short = "Failed to generate short summary."

        # Detailed Summary
        try:
            long_summary_resp = llm.invoke([
                SystemMessage(content="You are a professional document analysis assistant."),
                HumanMessage(content=(
                    "Please read the following text extracted from a PDF and generate a detailed, "
                    "structured summary in Markdown format. Include major themes, key findings, "
                    "and any important conclusions. Limit the response to 400 words:\n\n"
                    f"{text_for_summary}"
                ))
            ])
            doc.summary_long = long_summary_resp.content.strip()
        except Exception as le:
            logger.error(f"Failed to generate long summary for document {doc.id}: {str(le)}")
            doc.summary_long = "Failed to generate detailed summary."
            
        doc.status = 'ready'
        doc.processed_at = timezone.now()
        doc.save()
        logger.info(f"Document '{doc.title}' processing completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed to process document {doc.id}: {str(e)}")
        doc.status = 'failed'
        doc.error_message = str(e)
        doc.save()
