"""Downloads must remain verified without the build machine's CA paths."""
import io
import ssl

from scripts import import_cards


def test_bundled_roots_work_without_system_paths(monkeypatch, tmp_path):
    monkeypatch.setenv('SSL_CERT_FILE', str(tmp_path / 'missing.pem'))
    monkeypatch.setenv('SSL_CERT_DIR', str(tmp_path / 'missing-directory'))
    assert ssl.create_default_context().cert_store_stats()['x509_ca'] == 0
    import_cards._download_ssl_context.cache_clear()
    try:
        context = import_cards._download_ssl_context()
        assert context.cert_store_stats()['x509_ca'] > 0
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
    finally:
        import_cards._download_ssl_context.cache_clear()


def test_download_passes_verified_context(monkeypatch):
    calls = []

    def urlopen(request, *, timeout, context):
        calls.append((request.full_url, timeout, context))
        return io.BytesIO(b'catalog or artwork')

    monkeypatch.setattr(import_cards.urllib.request, 'urlopen', urlopen)
    assert import_cards._get('https://example.com/card') == b'catalog or artwork'
    assert calls[0][0:2] == ('https://example.com/card', 30.0)
    assert calls[0][2].check_hostname
    assert calls[0][2].verify_mode == ssl.CERT_REQUIRED
