import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)

def extract_and_chunk_pdf(file_path,title, chunk_size=1200, chunk_overlap=250):
    """
    Extracts text page-by-page from a PDF file using PyPDFLoader.

    Returns a tuple: (chunks, page_count, pdf_title)

    - chunks     : list of LangChain Document objects ready for embedding
    - page_count : total number of pages (derived from loader output)
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

    page_count = len(langchain_docs)

    # ── Chunk ─────────────────────────────────────────────────────────────────
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = text_splitter.split_documents(langchain_docs)

    logger.info(f"Successfully split PDF '{langchain_docs[0].metadata['title']}' into {len(chunks)} chunks.")
    return chunks, page_count, langchain_docs[0].metadata['title']

