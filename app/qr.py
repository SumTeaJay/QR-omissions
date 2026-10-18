from __future__ import annotations

"""QR image generation and decoding helpers."""

import io

import cv2
import numpy as np
import qrcode


def generate_qr_png(token: str, *, box_size: int = 10, border: int = 4) -> bytes:
    """Render a signed token as a PNG suitable for Telegram uploads."""
    if not token or not isinstance(token, str):
        raise ValueError("token must be a non-empty string")
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(token)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def decode_qr_bytes(image_bytes: bytes) -> str | None:
    """Decode the first QR payload from image bytes using OpenCV.

    ``None`` is returned when the bytes are not an image or no QR code can be
    detected.  The function deliberately does not validate token signatures;
    that belongs to the application service layer.
    """
    if not image_bytes:
        return None
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    detector = cv2.QRCodeDetector()
    value, _, _ = detector.detectAndDecode(image)
    value = value.strip() if value else ""
    return value or None


# Friendly aliases used by callers and tests.
create_qr_png = generate_qr_png
decode_qr = decode_qr_bytes
decode_qr_from_bytes = decode_qr_bytes
qr_to_png = generate_qr_png
