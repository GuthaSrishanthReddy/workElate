import socket

import pytest

from cli.sitecrawl.netguard import BlockedURL, guard_url, normalize_url


def test_only_http_schemes_are_allowed():
    for value in ("file:///etc/passwd", "ftp://example.com"):
        with pytest.raises(BlockedURL, match="Only http and https"):
            normalize_url(value)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000", "http://169.254.169.254", "http://10.0.0.2"])
def test_private_addresses_are_blocked(url):
    with pytest.raises(BlockedURL):
        guard_url(url)


def test_dns_results_are_checked(monkeypatch):
    def private_result(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", 80))]
    monkeypatch.setattr(socket, "getaddrinfo", private_result)
    with pytest.raises(BlockedURL):
        guard_url("http://example.test")


def test_normalize_drops_fragment_and_default_port():
    assert normalize_url("HTTPS://Example.com:443/about#team") == "https://example.com/about"
