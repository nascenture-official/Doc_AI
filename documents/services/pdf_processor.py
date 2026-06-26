import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

from documents.services.ocr_processor import needs_ocr, run_ocr_on_page, MAX_OCR_PAGES_PER_DOCUMENT

logger = logging.getLogger(__name__)

def extract_and_chunk_pdf(file_path,title, chunk_size=1200, chunk_overlap=250):
    """
    Extracts text page-by-page from a PDF file using PyPDFLoader.
    Pages with little/no extractable text (scanned/image-only pages) fall back
    to RapidOCR so scanned PDFs become searchable/chattable like native ones.

    Returns a tuple: (chunks, page_count, pdf_title, extraction_method)

    - chunks            : list of LangChain Document objects ready for embedding
    - page_count        : total number of pages (derived from loader output)
    - extraction_method : 'native' | 'ocr' | 'mixed'
    """
    try:
        loader = PyPDFLoader(file_path = file_path,mode='page')
        langchain_docs = loader.load()
    except Exception as e:
        logger.error(f"PyPDFLoader failed for {file_path}: {str(e)}")
        raise ValueError(f"Could not extract text from PDF: {str(e)}")

    if not langchain_docs:
        raise ValueError("No text could be extracted from this PDF document.")


    for doc in langchain_docs:
        doc.metadata["title"] = title

    # ── OCR fallback for scanned/image-only pages ───────────────────────────
    pages_needing_ocr = [i for i, d in enumerate(langchain_docs) if needs_ocr(d.page_content)]

    print(f"Pages needing OCR: {pages_needing_ocr}")

    extraction_method = "native"
    if pages_needing_ocr:
        if len(pages_needing_ocr) > MAX_OCR_PAGES_PER_DOCUMENT:
            logger.warning(
                f"{file_path}: {len(pages_needing_ocr)} pages need OCR, capping at "
                f"{MAX_OCR_PAGES_PER_DOCUMENT} to respect task timeout."
            )
            pages_needing_ocr = pages_needing_ocr[:MAX_OCR_PAGES_PER_DOCUMENT]

        for idx in pages_needing_ocr:
            langchain_docs[idx].page_content = run_ocr_on_page(file_path, idx)
            langchain_docs[idx].metadata["extraction_method"] = "ocr"

        extraction_method = "mixed" if len(pages_needing_ocr) < len(langchain_docs) else "ocr"

    for d in langchain_docs:
        d.metadata.setdefault("extraction_method", "native")

    page_count = len(langchain_docs)

    # ── Chunk ─────────────────────────────────────────────────────────────────
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = text_splitter.split_documents(langchain_docs)

    logger.info(f"Successfully split PDF '{langchain_docs[0].metadata['title']}' into {len(chunks)} chunks.")
    return chunks, page_count, langchain_docs[0].metadata['title'], extraction_method

