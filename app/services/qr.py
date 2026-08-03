from io import BytesIO

import qrcode

from app.core.config import settings


def status_path(slug: str, token: str) -> str:
    return f"/e/{slug}/t/{token}"


def status_url(slug: str, token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}{status_path(slug, token)}"


def qr_api_path(token: str) -> str:
    return f"/api/qr/{token}.png"


def make_qr_png(data: str) -> bytes:
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
