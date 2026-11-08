from app.protocol import PROTOCOL_VERSION, is_supported


def test_protocol_version_is_one():
    assert PROTOCOL_VERSION == 1


def test_is_supported_current_version():
    assert is_supported(PROTOCOL_VERSION) is True


def test_is_supported_rejects_higher_version():
    assert is_supported(PROTOCOL_VERSION + 1) is False


def test_is_supported_rejects_unknown_version():
    assert is_supported(0) is False
    assert is_supported(99) is False
