import fitz  # PyMuPDF
import pymupdf4llm
from langchain_core.documents import Document as LangChainDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)

def extract_and_chunk_pdf(file_path, title, chunk_size=800, chunk_overlap=100):
    """
    Extracts text page-by-page from a PDF file using pymupdf4llm.
    Then, chunks the extracted page content using LangChain's RecursiveCharacterTextSplitter,
    preserving page number and document title in each chunk's metadata.
    """
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        logger.error(f"Failed to open PDF file {file_path}: {str(e)}")
        raise ValueError(f"Could not open PDF file: {str(e)}")

    langchain_docs = []

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page_text = ""
        try:
            # pymupdf4llm.to_markdown takes a 0-indexed page list
            page_text = pymupdf4llm.to_markdown(file_path, pages=[page_idx])
        except Exception as e:
            logger.warning(f"pymupdf4llm failed on page {page_num} of {title}. Falling back to fitz. Error: {str(e)}")
            try:
                # Fallback to standard PyMuPDF extraction
                doc = fitz.open(file_path)
                page_text = doc[page_idx].get_text()
                doc.close()
            except Exception as fe:
                logger.error(f"PyMuPDF fallback failed on page {page_num}: {str(fe)}")
                continue

        if page_text and page_text.strip():
            langchain_docs.append(LangChainDocument(
                page_content=page_text,
                metadata={"source": title, "page": page_num}
            ))

    if not langchain_docs:
        raise ValueError("No text could be extracted from this PDF document.")

    # Split the documents into chunks using RecursiveCharacterTextSplitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len
    )

    chunks = text_splitter.split_documents(langchain_docs)

    # Filter out chunks that are too short to be meaningful (noise from headers, footers, etc.)
    chunks = [chunk for chunk in chunks if len(chunk.page_content.strip()) > 50]

    logger.info(f"Successfully split PDF '{title}' into {len(chunks)} chunks.")
    return chunks
