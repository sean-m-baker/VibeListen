import pytest
from unittest.mock import patch, MagicMock

from backend.parser import _validate_url, extract_article_content


class TestValidateURL:
    """SSRF validation — _validate_url rejects internal/private destinations."""

    def test_valid_external_url(self):
        """Well-formed public URL should pass validation."""
        assert _validate_url("https://example.com/article") == "https://example.com/article"

    def test_valid_http_url(self):
        assert _validate_url("http://example.com") == "http://example.com"

    def test_no_hostname_raises(self):
        with pytest.raises(ValueError, match="no hostname"):
            _validate_url("not-a-url")

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            _validate_url("ftp://files.example.com/data")

    def test_empty_scheme_raises(self):
        with pytest.raises(ValueError, match="no hostname"):
            _validate_url("javascript:alert(1)")

    def test_loopback_ip_raises(self):
        with pytest.raises(ValueError, match="internal/private"):
            _validate_url("http://127.0.0.1:8000/secret")

    def test_rfc1918_10_raises(self):
        with pytest.raises(ValueError, match="internal/private"):
            _validate_url("http://10.0.0.1/admin")

    def test_rfc1918_172_raises(self):
        with pytest.raises(ValueError, match="internal/private"):
            _validate_url("http://172.16.0.1/admin")

    def test_rfc1918_192_raises(self):
        with pytest.raises(ValueError, match="internal/private"):
            _validate_url("http://192.168.1.1/admin")

    def test_link_local_raises(self):
        with pytest.raises(ValueError, match="internal/private"):
            _validate_url("http://169.254.169.254/latest/meta-data/")

    def test_hostname_resolves_to_public_passes(self):
        """Hostnames that resolve to public IPs should be allowed."""
        assert _validate_url("http://example.com") == "http://example.com"

    def test_unresolvable_hostname_raises(self):
        """Unresolvable hostnames are treated as internal (safe default)."""
        with pytest.raises(ValueError, match="internal/private"):
            _validate_url("http://this-does-not-exist-totally.invalid/page")


class TestExtractArticleContent:
    """End-to-end pipeline with mocked HTTP responses."""

    SAMPLE_HTML = """
    <html><body>
        <nav>Nav links</nav>
        <article>
            <h1>Test Article</h1>
            <p>This is the first paragraph of the article.</p>
            <p>This is the second paragraph.</p>
        </article>
        <footer>Footer stuff</footer>
    </body></html>
    """

    @patch("backend.parser.requests.get")
    def test_successful_extraction(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = self.SAMPLE_HTML
        mock_response.encoding = "utf-8"
        mock_get.return_value = mock_response

        result = extract_article_content("https://example.com/article")
        assert "Test Article" in result
        assert "first paragraph" in result
        assert "second paragraph" in result
        assert "Nav links" not in result
        assert "Footer stuff" not in result

    @patch("backend.parser.requests.get")
    def test_ssrf_blocked_before_request(self, mock_get):
        """SSRF targets should be rejected without making any HTTP call."""
        with pytest.raises(RuntimeError, match="internal/private"):
            extract_article_content("http://127.0.0.1/secret")
        mock_get.assert_not_called()

    @patch("backend.parser.requests.get")
    def test_http_error_propagates(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="Failed to download"):
            extract_article_content("https://example.com/404")

    @patch("backend.parser.requests.get")
    def test_empty_content_raises(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"
        mock_response.encoding = "utf-8"
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="empty or unparsable"):
            extract_article_content("https://example.com/empty")
