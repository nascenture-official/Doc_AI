from django import template
from django.utils.safestring import mark_safe
import markdown as md_lib

register = template.Library()

@register.filter(name='markdown_to_html')
def markdown_to_html(value):
    """
    Renders raw markdown content into safe HTML using the python-markdown library.
    Allows basic formatting, tables, lists, and line-breaks.
    """
    if not value:
        return ""
    # Use standard extensions for tables, lists, code highlighting, and auto-newlines
    html_content = md_lib.markdown(value, extensions=['extra', 'nl2br'])
    return mark_safe(html_content)

import re
import json as _json
from django.utils.html import escape

@register.filter(name='highlight_search')
def highlight_search(text, search_term):
    """
    Case-insensitive search highlighting filter that highlights matching search terms
    within a block of text, escaping HTML to prevent XSS.
    """
    if not text:
        return ""
    escaped_text = escape(text)
    if not search_term:
        return mark_safe(escaped_text)
        
    escaped_term = escape(search_term)
    pattern = re.compile(re.escape(escaped_term), re.IGNORECASE)
    highlighted = pattern.sub(lambda m: f"<mark class='highlight-mark'>{m.group(0)}</mark>", escaped_text)
    return mark_safe(highlighted)


@register.filter(name='json_encode')
def json_encode(value):
    """
    Safely serialize a Python value to a JSON string for embedding in data-* attributes.
    Usage: {{ msg.sources|json_encode }}
    Never use |safe on user-controlled JSON — use this filter instead.
    """
    return _json.dumps(value or [])

