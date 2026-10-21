from app.qr import decode_qr_bytes, generate_qr_png


def test_qr_png_round_trip() -> None:
    token = "qr1.payload.signature"
    image = generate_qr_png(token)
    assert image.startswith(b"\x89PNG")
    assert decode_qr_bytes(image) == token


def test_qr_decoder_returns_none_for_invalid_bytes() -> None:
    assert decode_qr_bytes(b"not an image") is None
