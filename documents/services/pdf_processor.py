from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)

def extract_and_chunk_pdf(file_path, title, chunk_size=800, chunk_overlap=150):
    """
    Extracts text page-by-page from a PDF file using LangChain's PyMuPDF4LLMLoader.
    Each page is returned as a separate LangChain Document with markdown content.
    Then, chunks the extracted page content using LangChain's RecursiveCharacterTextSplitter,
    preserving page number and document title in each chunk's metadata.
    """
    try:
        loader = PyMuPDF4LLMLoader(file_path, mode="page")
        langchain_docs = loader.load()
    except Exception as e:
        logger.error(f"PyPDFLoader failed for {file_path}: {str(e)}")
        raise ValueError(f"Could not extract text from PDF: {str(e)}")

    if not langchain_docs:
        raise ValueError("No text could be extracted from this PDF document.")

    print("langchain_docs ==",langchain_docs)

    # Split the documents into chunks using RecursiveCharacterTextSplitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    chunks = text_splitter.split_documents(langchain_docs)

    logger.info(f"Successfully split PDF '{title}' into {len(chunks)} chunks.")
    return chunks
