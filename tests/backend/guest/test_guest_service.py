"""Adres goscia z naglowka nginx i jego HMAC (adres nie jest zapisywany)."""

from __future__ import annotations

import pytest

from src.backend.guest.service import client_address, client_hash


@pytest.mark.parametrize(
    ("forwarded", "peer", "expected"),
    [
        ("203.0.113.7", "172.18.0.3", "203.0.113.7"),
        # IPv6: cala siec /64 to jeden adres (zmiana adresu w sieci nie daje nowych sesji)
        (" 2001:db8:1:2::1 ", "172.18.0.3", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff::9", "172.18.0.3", "2001:db8:1:2::/64"),
        (None, "127.0.0.1", "127.0.0.1"),
        ("", "127.0.0.1", "127.0.0.1"),
        (None, None, "unknown"),
    ],
)
def test_client_address(forwarded, peer, expected):
    assert client_address(forwarded, peer) == expected


@pytest.mark.parametrize("forwarded", ["not-an-ip", "1.2.3.4, 5.6.7.8"])
def test_garbage_header_is_not_an_address(forwarded):
    # smieci nie trafiaja do wspolnego kubelka adresu polaczenia (nginx)
    assert client_address(forwarded, "172.18.0.3") is None


def test_client_hash_is_stable_and_keyed():
    first = client_hash("203.0.113.7", "secret-one")

    assert first == client_hash("203.0.113.7", "secret-one")
    assert first != client_hash("203.0.113.8", "secret-one")
    assert first != client_hash("203.0.113.7", "secret-two")
    assert "203.0.113.7" not in first
    assert len(first) == 64
