import base64
import mimetypes
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class FetchedImage:
    url: str
    content_type: str
    size_bytes: int
    data_uri: str


def fetch_public_image_as_data_uri(url: str, settings: Settings) -> FetchedImage:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("file_url debe ser una URL publica http o https")

    timeout = httpx.Timeout(settings.image_download_timeout_seconds)
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
        response.raise_for_status()
        content_type = _normalize_content_type(response.headers.get("content-type"), parsed.path)
        if not content_type.startswith("image/"):
            raise ValueError(f"file_url no apunta a una imagen valida: {content_type}")

        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > settings.max_image_bytes:
                raise ValueError("La imagen supera el tamano maximo permitido")

    encoded = base64.b64encode(bytes(content)).decode("ascii")
    return FetchedImage(
        url=url,
        content_type=content_type,
        size_bytes=len(content),
        data_uri=f"data:{content_type};base64,{encoded}",
    )


def _normalize_content_type(header_value: str | None, path: str) -> str:
    if header_value:
        return header_value.split(";", 1)[0].strip().lower()

    guessed_type, _ = mimetypes.guess_type(path)
    if guessed_type:
        return guessed_type.lower()
    return "application/octet-stream"
