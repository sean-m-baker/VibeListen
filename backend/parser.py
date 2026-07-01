import logging
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.auth import is_internal_ip

logger = logging.getLogger("VibeListen.Parser")

# Reusable HTTP session with connection pooling (Keep-Alive)
_HTTP_SESSION = requests.Session()


def _validate_url(url: str) -> str:
    """Validate *url* is safe to fetch — resolves DNS once to check for
    internal IPs, then returns the original URL for the actual request.

    We keep the original hostname in the request URL so that SSL/TLS
    certificate verification works correctly (certificates are issued
    for hostnames, not IP addresses). The TOCTOU window between the
    validation resolution and the actual request is small; a full DNS
    rebinding mitigation would require a custom transport adapter that
    pins the resolved IP during the SSL handshake.
    """
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addrs = socket.getaddrinfo(parsed.hostname, port)
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {parsed.hostname}")

    resolved_ip = addrs[0][4][0]
    if is_internal_ip(resolved_ip):
        raise ValueError(f"Blocked request to internal/private IP: {resolved_ip}")

    return url


def extract_article_content(url: str) -> str:
    """
    Fetches raw HTML from a URL, strips out boilerplate (navigation bars, footers, 
    ads, cookie popups), and returns a clean plain text representation.
    """
    # Use a standard desktop browser user agent to avoid bot detection/blocking
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    try:
        _validate_url(url)

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError)),
        )
        def _fetch_url(url: str) -> requests.Response:
            return _HTTP_SESSION.get(url, headers=headers, timeout=(10, 30))

        response = _fetch_url(url)
        response.raise_for_status()
        
        # Support correct encoding detection
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding
            
        html = response.text
    except Exception as e:
        raise RuntimeError(f"Failed to download webpage: {str(e)}")

    try:
        # Pass raw HTML to readability-lxml Document parser
        doc = Document(html)
        summary_html = doc.summary()  # Isolates main readable block in clean HTML
        
        # Parse output with BeautifulSoup to extract plain text
        soup = BeautifulSoup(summary_html, "lxml")
        
        # Remove any unwanted inline media/scripts that might have slipped through
        for element in soup(["script", "style", "nav", "header", "footer", "iframe", "video", "audio"]):
            element.decompose()

        # Extract text paragraph-by-paragraph to preserve structural gaps
        # We target main textual structural blocks: p, li, and header tags
        blocks = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "blockquote"])
        
        paragraphs = []
        for block in blocks:
            text = block.get_text().strip()
            # Skip short recurring links or empty blocks
            if text:
                paragraphs.append(text)

        # Merge blocks into a single plain-text string separated by double newlines
        clean_text = "\n\n".join(paragraphs)
        
        # Fallback to general text extraction if tag parsing yielded nothing
        if not clean_text.strip():
            clean_text = soup.get_text(separator="\n\n").strip()

        if not clean_text.strip():
            raise ValueError("Webpage content is empty or unparsable.")

        return clean_text
    except Exception as e:
        raise RuntimeError(f"Failed to parse readable content: {str(e)}")
