from pypdf import PdfReader

def get_pdf_page_count(file_path_or_handle):
    """
    Extracts the page count from a PDF file.
    Returns the page count, or 0 if parsing fails.
    """
    try:
        reader = PdfReader(file_path_or_handle)
        return len(reader.pages)
    except Exception:
        return 0
