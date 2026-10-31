import pytest

from src.bot.core import build_telegram_session


def test_direct_session_ignores_env_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://claude-proxy:3128")
    assert build_telegram_session("")._proxy is None


@pytest.mark.parametrize(
    "url",
    ["socks5://user:pw@proxy.example:1080", "http://proxy.example:3128"],
)
def test_proxy_url_is_applied(url):
    assert build_telegram_session(url)._proxy == url


def test_bad_scheme_is_rejected():
    with pytest.raises(ValueError):
        build_telegram_session("ftp://proxy.example:21")


def test_socks5h_is_treated_as_socks5():
    assert build_telegram_session("socks5h://proxy.example:1080")._proxy == "socks5://proxy.example:1080"
