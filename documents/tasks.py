import logging
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from documents.models import Document
from documents.services.pdf_processor import extract_and_chunk_pdf
from documents.services.vector_store import create_vector_index
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def process_uploaded_document(self, document_id):
    """
    Background worker task to process an uploaded document:
    1. Extracts and chunks text using PyMuPDF/pymupdf4llm & LangChain.
    2. Upserts dense + sparse (BM25) vectors into Pinecone.
    3. Updates document status to 'ready' (or 'failed' if error).
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
        langchain_chunks, page_count, pdf_title, extraction_method = extract_and_chunk_pdf(doc.file.path,doc.title)

        # Save page count and resolved PDF title back to the document record
        doc.page_count = page_count
        doc.extraction_method = extraction_method
        if pdf_title:
            doc.title = pdf_title

        # Step 2: Upsert dense + sparse vectors into Pinecone
        logger.info(f"Upserting Pinecone vectors for document '{doc.title}'...")
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

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_summary_task(self, document_id, summary_type):
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
        langchain_chunks, _, _, _ = extract_and_chunk_pdf(doc.file.path, doc.title)
        
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

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def translate_document_task(self, document_id, language):
    """
    Background worker task to translate a document into a specified language.
    """
    from documents.models import DocumentTranslation
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist.")
        return

    translation, created = DocumentTranslation.objects.get_or_create(
        document=doc, language=language,
        defaults={'status': 'processing'}
    )
    if not created and translation.status == 'ready':
        return  # already translated

    translation.status = 'processing'
    translation.save()

    try:
        logger.info(f"Extracting text for document '{doc.title}' for translation to {language}...")
        langchain_chunks, _, _, _ = extract_and_chunk_pdf(doc.file.path, doc.title)
        
        full_text = "\n\n".join([chunk.page_content for chunk in langchain_chunks])
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )
        
        # Get language name
        from documents.models import TRANSLATION_LANGUAGES
        lang_dict = dict(TRANSLATION_LANGUAGES)
        language_name = lang_dict.get(language, language)

        max_chars = 300000  # safe token limit approximation
        text_for_translation = full_text[:max_chars]

        resp = llm.invoke([
            SystemMessage(content="You are a professional document translator. Please preserve formatting and Markdown structure where possible."),
            HumanMessage(content=(
                f"Please translate the following document text into {language_name}. "
                "Output ONLY the translated text in Markdown format:\n\n"
                f"{text_for_translation}"
            ))
        ])
        
        translation.translated_text = resp.content.strip()
        translation.status = 'ready'
        translation.save()
        logger.info(f"Successfully generated translation ({language}) for document '{doc.title}'.")
        
    except Exception as e:
        logger.error(f"Failed to generate translation ({language}) for document {doc.id}: {str(e)}")
        translation.status = 'failed'
        translation.error_message = str(e)
        translation.save()

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def rewrite_content_task(self, document_id, style):
    """
    Background worker task to rewrite a document in a specified style.
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist.")
        return

    try:
        logger.info(f"Extracting text for document '{doc.title}' for rewriting in {style} style...")
        langchain_chunks, _, _, _ = extract_and_chunk_pdf(doc.file.path, doc.title)
        
        full_text = "\n\n".join([chunk.page_content for chunk in langchain_chunks])
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )
        
        max_chars = 100000
        text_for_rewrite = full_text[:max_chars]

        resp = llm.invoke([
            SystemMessage(content=f"You are a professional document writer. Your task is to rewrite the provided text in a {style} style. Preserve the core meaning but adjust the tone and structure to fit the {style} style."),
            HumanMessage(content=(
                f"Please rewrite the following document text in a {style} style. "
                "Output ONLY the rewritten text in Markdown format:\n\n"
                f"{text_for_rewrite}"
            ))
        ])
        
        doc.rewrite_content = resp.content.strip()
        doc.rewrite_style = style
        doc.save()
        logger.info(f"Successfully generated rewrite ({style}) for document '{doc.title}'.")
        
    except Exception as e:
        logger.error(f"Failed to generate rewrite ({style}) for document {doc.id}: {str(e)}")
        doc.rewrite_content = "Failed to rewrite content."
        doc.save()


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def extract_key_points_task(self, document_id):
    """
    Background worker task to extract key points from a document.
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist.")
        return

    try:
        logger.info(f"Extracting text for document '{doc.title}' to extract key points...")
        langchain_chunks, _, _, _ = extract_and_chunk_pdf(doc.file.path, doc.title)
        
        full_text = "\n\n".join([chunk.page_content for chunk in langchain_chunks])
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )
        
        max_chars = 100000
        text_for_key_points = full_text[:max_chars]

        resp = llm.invoke([
            SystemMessage(content="You are a professional document analyst. Your task is to extract the most important key points from the provided text."),
            HumanMessage(content=(
                "Please extract the key points from the following document text. "
                "Output ONLY a structured list of key points in Markdown bullet points:\n\n"
                f"{text_for_key_points}"
            ))
        ])
        
        doc.key_points = resp.content.strip()
        doc.save()
        logger.info(f"Successfully extracted key points for document '{doc.title}'.")
        
    except Exception as e:
        logger.error(f"Failed to extract key points for document {doc.id}: {str(e)}")
        doc.key_points = "Failed to extract key points."
        doc.save()


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_faqs_task(self, document_id):
    """
    Background worker task to generate FAQs from a document.
    """
    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} does not exist.")
        return

    try:
        logger.info(f"Extracting text for document '{doc.title}' to generate FAQs...")
        langchain_chunks, _, _, _ = extract_and_chunk_pdf(doc.file.path, doc.title)
        
        full_text = "\n\n".join([chunk.page_content for chunk in langchain_chunks])
        
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )
        
        max_chars = 100000
        text_for_faqs = full_text[:max_chars]

        resp = llm.invoke([
            SystemMessage(content="You are a professional document analyst. Your task is to generate 8-12 frequently asked questions (FAQs) based on the provided text."),
            HumanMessage(content=(
                "Please generate 8-12 FAQ pairs based on the following document text. "
                "Output ONLY the FAQs in Markdown format with '## Q' and 'A' structure:\n\n"
                f"{text_for_faqs}"
            ))
        ])
        
        doc.faqs = resp.content.strip()
        doc.save()
        logger.info(f"Successfully generated FAQs for document '{doc.title}'.")
        
    except Exception as e:
        logger.error(f"Failed to generate FAQs for document {doc.id}: {str(e)}")
        doc.faqs = "Failed to generate FAQs."
        doc.save()

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def compare_documents_task(self, comparison_id):
    """
    Background worker task to compare two documents.
    1. Extracts clean, page-ordered text from both PDFs using PyMuPDF.
    2. Normalizes text to avoid noisy diffs (strip spaces, collapse blank lines).
    3. Generates a unified diff using difflib.
    4. Generates an AI summary of the differences.
    """
    from documents.models import DocumentComparison
    import difflib
    import re
    import fitz  # PyMuPDF

    try:
        comparison = DocumentComparison.objects.get(id=comparison_id)
    except DocumentComparison.DoesNotExist:
        logger.error(f"DocumentComparison with ID {comparison_id} does not exist.")
        return

    def normalize_text(text):
        """
        Normalize text to reduce noisy diffs caused by formatting differences.
        - Strips leading/trailing whitespace per line.
        - Collapses 3+ consecutive blank lines into a single blank line.
        """
        lines = text.splitlines()
        stripped_lines = [line.strip() for line in lines]
        joined_text = "\n".join(stripped_lines)
        normalized = re.sub(r'\n{3,}', '\n\n', joined_text)
        return normalized.strip()

    def extract_full_text(file_path):
        """
        Extract clean, page-ordered text from a PDF using PyMuPDF.
        Using this instead of extract_and_chunk_pdf to avoid:
        - Overlapping chunk content producing duplicate text in the diff.
        - Chunks being joined out of page order.
        """
        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return "\n\n".join(pages)

    try:
        # Set status to processing inside try so any failure
        # correctly falls through to the except block and marks as 'failed'
        # instead of getting stuck at 'processing' forever.
        comparison.status = 'processing'
        comparison.save()

        logger.info(f"Extracting text for comparison {comparison.id}...")
        base_text = extract_full_text(comparison.document_base.file.path)
        compare_text = extract_full_text(comparison.document_compare.file.path)

        # Normalize both texts
        base_normalized = normalize_text(base_text)
        compare_normalized = normalize_text(compare_text)

        # Generate unified diff
        logger.info(f"Generating diff for comparison {comparison.id}...")
        base_lines = base_normalized.splitlines(keepends=True)
        compare_lines = compare_normalized.splitlines(keepends=True)

        diff = difflib.unified_diff(
            base_lines,
            compare_lines,
            fromfile=comparison.document_base.title,
            tofile=comparison.document_compare.title,
            n=3  # Lines of context around each change
        )
        diff_text = "".join(diff)

        # Handle identical documents — set a sentinel value so the
        # frontend can render a clean "no differences" message instead
        # of a blank/broken diff2html view.
        if not diff_text.strip():
            comparison.diff_data = "NO_DIFF"
            comparison.ai_summary = "No meaningful differences were detected between the two documents."
            comparison.status = 'ready'
            comparison.save()
            logger.info(f"Documents are identical for comparison {comparison.id}.")
            return

        comparison.diff_data = diff_text

        # Generate AI summary
        logger.info(f"Generating AI summary for comparison {comparison.id}...")
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.2
        )

        # Truncate diff for the prompt if it's too large.
        # Inform the model when truncation occurs so it can note
        # that the summary may not cover all changes.
        truncated = len(diff_text) > 50000
        diff_for_summary = diff_text[:50000]

        truncation_notice = (
            "\n\nNOTE: The diff was truncated to the first 50,000 characters. "
            "Your summary may not reflect all changes in the document.\n\n"
            if truncated else ""
        )

        resp = llm.invoke([
            SystemMessage(content=(
                "You are a professional document analyst. "
                "Your task is to summarize the differences between two versions "
                "of a document based on the provided unified diff."
            )),
            HumanMessage(content=(
                "Please provide a plain-English summary of the meaningful changes "
                "between these two documents. Focus on what was added, removed, or "
                "modified. Keep it concise but informative (max 300 words). "
                "Format the response using Markdown bullet points."
                f"{truncation_notice}"
                f"\n\nDiff Data:\n{diff_for_summary}"
            ))
        ])
        comparison.ai_summary = resp.content.strip()

        # Append a visible warning to the summary if diff was truncated,
        # so users know the summary is partial.
        if truncated:
            comparison.ai_summary += (
                "\n\n> **Note:** This summary is based on a partial diff. "
                "The documents are large and only the first portion of changes "
                "was analyzed."
            )

        comparison.status = 'ready'
        comparison.save()
        logger.info(f"Successfully processed comparison {comparison.id}.")

    except Exception as e:
        logger.error(f"Failed to process comparison {comparison.id}: {str(e)}")
        comparison.status = 'failed'
        comparison.error_message = str(e)
        comparison.save()