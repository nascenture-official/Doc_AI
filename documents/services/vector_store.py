import os
import logging
from django.conf import settings
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

def get_embeddings_instance():
    """
    Returns an instance of OpenAIEmbeddings using settings configured in Django settings.
    """
    api_key = getattr(settings, 'OPENAI_API_KEY', None)
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key
    )

def create_faiss_index(document_id, langchain_documents):
    """
    Generates embeddings for a list of LangChain documents and creates a local FAISS index.
    Saves the index files to vector_store/<document_id>/.
    """
    try:
        embeddings = get_embeddings_instance()
        db = FAISS.from_documents(langchain_documents, embeddings)
        
        # Define saving path
        vector_store_dir = os.path.join(settings.BASE_DIR, "vector_store", str(document_id))
        os.makedirs(vector_store_dir, exist_ok=True)
        
        db.save_local(vector_store_dir)
        logger.info(f"Successfully created and saved FAISS index for document {document_id} at {vector_store_dir}")
        return True
    except Exception as e:
        logger.error(f"Failed to create FAISS index for document {document_id}: {str(e)}")
        raise e

def load_faiss_index(document_id):
    """
    Loads a single FAISS vector index from disk.
    """
    embeddings = get_embeddings_instance()
    vector_store_dir = os.path.join(settings.BASE_DIR, "vector_store", str(document_id))
    
    if not os.path.exists(vector_store_dir):
        raise FileNotFoundError(f"Vector store directory for document {document_id} does not exist at {vector_store_dir}")
        
    db = FAISS.load_local(vector_store_dir, embeddings, allow_dangerous_deserialization=True)
    return db

def load_multiple_indexes(document_ids):
    """
    Loads and merges FAISS vector indexes for multiple document IDs.
    Returns the merged FAISS index, or None if no indexes could be loaded.
    """
    merged_db = None
    for doc_id in document_ids:
        try:
            db = load_faiss_index(doc_id)
            if merged_db is None:
                merged_db = db
            else:
                merged_db.merge_from(db)
        except Exception as e:
            logger.warning(f"Failed to load FAISS index for document {doc_id}: {str(e)}")
            continue
    return merged_db

def delete_faiss_index(document_id):
    """
    Deletes the FAISS vector index directory from disk for a given document.
    """
    import shutil
    vector_store_dir = os.path.join(settings.BASE_DIR, "vector_store", str(document_id))
    if os.path.exists(vector_store_dir):
        try:
            shutil.rmtree(vector_store_dir)
            logger.info(f"Successfully deleted vector store directory: {vector_store_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete vector store directory {vector_store_dir}: {str(e)}")
            return False
    return False

def keyword_search_in_vectors(document_ids, query):
    """
    Performs a simple keyword/phrase search directly in the raw text documents stored
    inside the serialized FAISS indices, without any AI/LLM API calls.
    Returns list of dicts: [{'text': str, 'page': int, 'source': str}]
    """
    db = load_multiple_indexes(document_ids)
    if not db:
        return []
    
    matches = []
    query_lower = query.lower()
    
    # Iterate through all documents stored in the index docstore
    for doc in db.docstore._dict.values():
        if query_lower in doc.page_content.lower():
            matches.append({
                "text": doc.page_content,
                "page": doc.metadata.get("page", 1),
                "source": doc.metadata.get("source", "Unknown")
            })
            
    return matches
