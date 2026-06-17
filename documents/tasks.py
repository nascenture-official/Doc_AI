import logging
from django.utils import timezone
from django.conf import settings
from documents.models import Document
from documents.services.pdf_processor import extract_and_chunk_pdf
from documents.services.vector_store import create_vector_index
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
        
        # Step 2: Build Chroma index (saves text + vectors locally on disk)
        logger.info(f"Creating Chroma index for document '{doc.title}'...")
        create_vector_index(doc.id, doc.user_id, langchain_chunks)
        
        doc.status = 'ready'
        doc.processed_at = timezone.now()
        doc.save()
        logger.info(f"Document '{doc.title}' processing completed successfully.")
        
    except Exception as e:
        logger.error(f"Failed to process document {doc.id}: {str(e)}")
        doc.status = 'failed'
        doc.error_message = str(e)
        doc.save()

def generate_summary_task(document_id, summary_type):
    """
    Background worker task to generate a short or detailed summary for a document.
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist.")
        return

    try:
        logger.info(f"Extracting text for document '{doc.title}' to generate {summary_type} summary...")
        langchain_chunks = extract_and_chunk_pdf(doc.file.path, doc.title)
        
        full_text = "\n\n".join([chunk.page_content for chunk in langchain_chunks])
        max_chars = 100000  # ~25k tokens
        text_for_summary = full_text[:max_chars]
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )
        
        if summary_type == 'short':
            resp = llm.invoke([
                SystemMessage(content="You are a professional document analysis assistant."),
                HumanMessage(content=(
                    "Please read the following text extracted from a PDF and generate a concise summary "
                    "in 3-4 bullet points (maximum 120 words). Focus only on key takeaways:\n\n"
                    f"{text_for_summary}"
                ))
            ])
            doc.summary_short = resp.content.strip()
            
        elif summary_type == 'detailed':
            resp = llm.invoke([
                SystemMessage(content="You are a professional document analysis assistant."),
                HumanMessage(content=(
                    "Please read the following text extracted from a PDF and generate a detailed, "
                    "structured summary in Markdown format. Include major themes, key findings, "
                    "and any important conclusions. Limit the response to 400 words:\n\n"
                    f"{text_for_summary}"
                ))
            ])
            doc.summary_long = resp.content.strip()
            
        doc.save()
        logger.info(f"Successfully generated {summary_type} summary for document '{doc.title}'.")
        
    except Exception as e:
        logger.error(f"Failed to generate {summary_type} summary for document {doc.id}: {str(e)}")
        if summary_type == 'short':
            doc.summary_short = "Failed to generate short summary."
        else:
            doc.summary_long = "Failed to generate detailed summary."
        doc.save()

