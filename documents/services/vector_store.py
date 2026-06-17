import os
import logging
from django.conf import settings
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def get_embeddings_instance():
    """
    Returns an instance of OpenAIEmbeddings using settings configured in Django settings.
    Wrapped in CacheBackedEmbeddings for caching.
    """
    base_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    cache_dir = os.path.join(settings.BASE_DIR, "embedding_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    embedding_file_store = LocalFileStore(cache_dir)
    
    cached_embeddings = CacheBackedEmbeddings.from_bytes_store(
        base_embeddings,
        embedding_file_store,
        namespace=base_embeddings.model,
        query_embedding_cache=True,
        key_encoder="blake2b",
    )
    
    return cached_embeddings

def get_vector_store():
    """
    Returns the singleton centralized Chroma vector store instance.
    """
    persist_dir = os.path.join(settings.BASE_DIR, "chroma_db")
    embeddings = get_embeddings_instance()
    
    return Chroma(
        collection_name="documents_collection",
        embedding_function=embeddings,
        persist_directory=persist_dir
    )

def create_vector_index(document_id, user_id, langchain_documents):
    """
    Generates embeddings for a list of LangChain documents and adds them to the centralized Chroma DB.
    """
    try:
        # Inject document_id and user_id into metadata for all documents
        for doc in langchain_documents:
            doc.metadata["document_id"] = str(document_id)
            doc.metadata["user_id"] = str(user_id)
            
        db = get_vector_store()
        db.add_documents(langchain_documents)
        logger.info(f"Successfully added document {document_id} to centralized Chroma DB")
        return True
    except Exception as e:
        logger.error(f"Failed to add document {document_id} to Chroma DB: {str(e)}")
        raise e

def delete_vector_index(document_id):
    """
    Deletes documents matching the given document_id from the centralized Chroma DB.
    """
    try:
        db = get_vector_store()
        # Use underlying Chroma collection to delete by metadata filter
        db._collection.delete(where={"document_id": str(document_id)})
        logger.info(f"Successfully deleted vectors for document {document_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete vectors for document {document_id}: {str(e)}")
        return False

def keyword_search_in_vectors(query,user_id=None):
    """
    Performs a simple keyword/phrase search directly in the raw text documents stored
    inside the Chroma collection.
    Returns list of dicts: [{'text': str, 'page': int, 'source': str}]
    """
    db = get_vector_store()
    
    where_clause = {}
    if user_id:
        where_clause["user_id"] = str(user_id)
    else:
        return []
    
    # Get raw documents from the collection matching the filter
    try:
        results = db._collection.get(
            where=where_clause,
            where_document={"$contains": query},
            include=["documents", "metadatas"]
        )
    except Exception as e:
        logger.error(f"Failed to fetch documents for keyword search: {str(e)}")
        return []
        
    matches = []
    
    documents = results.get("documents", [])
    metadatas = results.get("metadatas", [])
    
    for text, meta in zip(documents, metadatas):
        matches.append({
            "text": text,
            "page": meta.get("page", 1) if meta else 1,
            "source": meta.get("source", "Unknown") if meta else "Unknown"
        })
            
    return matches
