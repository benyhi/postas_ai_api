from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography import x509
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from app.core.config import Settings, get_settings


class CredentialConfigurationError(RuntimeError):
    pass


class CredentialDecryptionError(RuntimeError):
    pass


class CredentialValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CertificateMetadata:
    fingerprint: str
    expires_at: datetime


@dataclass(frozen=True)
class DecryptedCredentials:
    certificate: str
    private_key: str
    access_token: str


class CredentialCipher:
    def __init__(self, keys: dict[str, Fernet], active_key_id: str) -> None:
        if not keys:
            raise CredentialConfigurationError("ARCA_CREDENTIAL_MASTER_KEYS no esta configurado.")
        if not active_key_id or active_key_id not in keys:
            raise CredentialConfigurationError("ARCA_CREDENTIAL_ACTIVE_KEY_ID no identifica una clave disponible.")
        self.keys = keys
        self.active_key_id = active_key_id

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "CredentialCipher":
        settings = settings or get_settings()
        raw = settings.arca_credential_master_keys
        if not raw:
            raise CredentialConfigurationError("ARCA_CREDENTIAL_MASTER_KEYS no esta configurado.")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CredentialConfigurationError("ARCA_CREDENTIAL_MASTER_KEYS debe ser un objeto JSON.") from exc
        if not isinstance(parsed, dict) or not parsed:
            raise CredentialConfigurationError("ARCA_CREDENTIAL_MASTER_KEYS debe contener al menos una clave.")
        keys: dict[str, Fernet] = {}
        try:
            for key_id, key_value in parsed.items():
                if not isinstance(key_id, str) or not isinstance(key_value, str):
                    raise ValueError
                keys[key_id] = Fernet(key_value.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise CredentialConfigurationError("El keyring ARCA contiene una clave Fernet invalida.") from exc
        return cls(keys, settings.arca_credential_active_key_id or "")

    def encrypt(self, value: str) -> str:
        if not value or not value.strip():
            raise CredentialValidationError("Los secretos ARCA no pueden estar vacios.")
        return self.keys[self.active_key_id].encrypt(value.strip().encode("utf-8")).decode("ascii")

    def decrypt(self, value: str, key_id: str) -> str:
        cipher = self.keys.get(key_id)
        if cipher is None:
            raise CredentialDecryptionError("La clave requerida para descifrar las credenciales no esta disponible.")
        try:
            return cipher.decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise CredentialDecryptionError("No fue posible descifrar las credenciales ARCA.") from exc


def validate_credential_material(certificate_pem: str, private_key_pem: str, cuit: str) -> CertificateMetadata:
    try:
        certificate = x509.load_pem_x509_certificate(certificate_pem.strip().encode("utf-8"))
    except ValueError as exc:
        raise CredentialValidationError("El certificado X.509 no tiene un PEM valido.") from exc
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.strip().encode("utf-8"), password=None
        )
    except (TypeError, ValueError) as exc:
        raise CredentialValidationError("La clave privada no tiene un PEM valido o esta protegida.") from exc

    certificate_public = certificate.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    private_public = private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    if certificate_public != private_public:
        raise CredentialValidationError("El certificado y la clave privada no corresponden.")

    now = datetime.now(timezone.utc)
    not_before = certificate.not_valid_before_utc
    not_after = certificate.not_valid_after_utc
    if now < not_before:
        raise CredentialValidationError("El certificado ARCA todavia no esta vigente.")
    if now >= not_after:
        raise CredentialValidationError("El certificado ARCA esta vencido.")

    subject_numbers = certificate.subject.get_attributes_for_oid(NameOID.SERIAL_NUMBER)
    if not subject_numbers:
        raise CredentialValidationError("El certificado ARCA no informa el CUIT del titular.")
    subject_digits = re.sub(r"\D", "", subject_numbers[0].value)
    if cuit not in subject_digits:
        raise CredentialValidationError("El CUIT no coincide con el certificado ARCA.")

    return CertificateMetadata(
        fingerprint=certificate.fingerprint(hashes.SHA256()).hex(),
        expires_at=not_after,
    )
