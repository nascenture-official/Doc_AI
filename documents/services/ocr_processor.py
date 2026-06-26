import re
import logging
import fitz  # PyMuPDF
from rapidocr import RapidOCR

logger = logging.getLogger(__name__)

MIN_CHARS_PER_PAGE = 20          # below this non-whitespace char count, treat page as scanned
OCR_RENDER_DPI = 200             # sweet spot for OCR legibility vs. speed
MAX_OCR_PAGES_PER_DOCUMENT = 50  # safeguard vs. Q_CLUSTER's 600s task timeout

_ocr_engine = None  # lazy singleton — model load is expensive


def needs_ocr(text: str) -> bool:
    """A page with fewer than MIN_CHARS_PER_PAGE non-whitespace chars is treated as scanned."""
    stripped = re.sub(r"\s+", "", text or "")
    return len(stripped) < MIN_CHARS_PER_PAGE


def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = RapidOCR()
    return _ocr_engine


def run_ocr_on_page(pdf_path: str, page_number: int) -> str:
    """
    Renders a single page to an image and runs RapidOCR on it.
    page_number is 0-indexed, matching PyPDFLoader's metadata["page"] convention.
    Never raises — returns "" on any failure so one bad page can't fail the whole document.
    """
    try:
        with fitz.open(pdf_path) as pdf:
            page = pdf[page_number]
            zoom = OCR_RENDER_DPI / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            img_bytes = pix.tobytes("png")

        result = get_ocr_engine()(img_bytes)
        if result is None or not result.txts:
            return ""
        return "\n".join(result.txts)
    except Exception as e:
        logger.warning(f"RapidOCR failed on page {page_number} of {pdf_path}: {e}")
        return ""
