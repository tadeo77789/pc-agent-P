import pytest

from paula_agent.messaging.signing import (
    SENT_AT_HEADER,
    SIGNATURE_HEADER,
    InvalidSignature,
    sign,
    verify,
)

SECRET = "s3cret"
BODY = b'{"id": "1"}'


def test_signed_message_verifies():
    headers = sign(SECRET, BODY, now=1000)

    verify(SECRET, BODY, headers, now=1010)


def test_tampered_body_is_rejected():
    headers = sign(SECRET, BODY, now=1000)

    with pytest.raises(InvalidSignature):
        verify(SECRET, b'{"id": "2"}', headers, now=1000)


def test_wrong_secret_is_rejected():
    headers = sign("other", BODY, now=1000)

    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, headers, now=1000)


def test_missing_headers_are_rejected():
    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, None)


def test_old_message_is_rejected():
    headers = sign(SECRET, BODY, now=1000)

    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, headers, max_age_seconds=60, now=2000)


def test_changed_timestamp_breaks_signature():
    headers = sign(SECRET, BODY, now=1000)
    headers[SENT_AT_HEADER] = "1500"

    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, headers, now=1500)
    assert SIGNATURE_HEADER in headers


def test_empty_secret_cannot_sign():
    with pytest.raises(ValueError):
        sign("", BODY)
