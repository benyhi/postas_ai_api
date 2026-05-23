from app.main import app
from app.core.config import get_settings
from app.providers.registry import get_provider
from app.services.images import fetch_public_image_as_data_uri


IMAGE_URL = (
    "https://pub-0d42ca5fbf2c419e9e07d8d67965889f.r2.dev/"
    "00000000-0000-0000-0000-000000000001/invoices/invoice_1.png"
)


def analizar_imagen(image_url: str = IMAGE_URL, provider_name: str = "google_genai") -> str:
    fetched_image = fetch_public_image_as_data_uri(image_url, get_settings())
    provider = get_provider(provider_name)
    result = provider.extract_invoice(fetched_image.data_uri)
    return result.data.model_dump_json()


if __name__ == "__main__":
    print(analizar_imagen())
