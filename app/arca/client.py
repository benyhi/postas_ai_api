from __future__ import annotations

import http.client
import json
import ssl
from dataclasses import dataclass
from typing import Any

from app.arca.crypto import DecryptedCredentials


AFIP_SDK_HOST = "app.afipsdk.com"


class ArcaClientError(Exception):
    pass


class ArcaHTTPError(ArcaClientError):
    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class ArcaClientOptions:
    cuit: str
    environment: str
    credentials: DecryptedCredentials
    timeout_seconds: float
    production_calls_enabled: bool


def _safe_error_message(raw: bytes, status_code: int) -> str:
    default = f"Afip SDK respondio con HTTP {status_code}."
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return default
    if isinstance(decoded, dict):
        for key in ("message", "error", "detail"):
            value = decoded.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    return default


class JsonTransport:
    def __init__(self, timeout: float) -> None:
        if timeout <= 0:
            raise ValueError("El timeout ARCA debe ser positivo.")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict:
        connection = http.client.HTTPSConnection(
            AFIP_SDK_HOST,
            timeout=self.timeout,
            context=ssl.create_default_context(),
        )
        response = None
        try:
            connection.request(method, path, json.dumps(payload), headers)
            response = connection.getresponse()
            raw = response.read()
        finally:
            connection.close()
        if response is None:
            raise ArcaClientError("Afip SDK no devolvio una respuesta.")
        if response.status >= 400:
            raise ArcaHTTPError(response.status, _safe_error_message(raw, response.status))
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArcaClientError("Afip SDK devolvio una respuesta invalida.") from exc
        if not isinstance(result, dict):
            raise ArcaClientError("Afip SDK devolvio un formato inesperado.")
        return result


def create_arca_client(options: ArcaClientOptions):
    if options.environment not in {"development", "production"}:
        raise ValueError("Ambiente ARCA invalido.")
    production = options.environment == "production"
    if production and not options.production_calls_enabled:
        raise ArcaClientError("Las llamadas ARCA de produccion estan deshabilitadas en esta instancia.")

    from afip import Afip
    from afip.electronic_billing import ElectronicBilling

    transport = JsonTransport(options.timeout_seconds)

    class TimeoutElectronicBilling(ElectronicBilling):
        def __init__(self, afip):
            super().__init__(afip)
            self.WSDL = ElectronicBilling.WSDL
            self.URL = ElectronicBilling.URL
            self.WSDL_TEST = ElectronicBilling.WSDL_TEST
            self.URL_TEST = ElectronicBilling.URL_TEST
            self.soapv12 = True

        def executeRequest(self, operation: str, params: dict | None = None):
            request_params = dict(params or {})
            request_params.update(self.getWSInitialRequest(operation))
            payload = {
                "method": operation,
                "params": request_params,
                "environment": self.afip.environment,
                "wsid": self.options.get("service"),
                "url": self.URL if self.afip.production else self.URL_TEST,
                "wsdl": self.WSDL if self.afip.production else self.WSDL_TEST,
                "soap_v_1_2": self.soapv12,
            }
            response = transport.request("POST", "/api/v1/afip/requests", payload, self.afip._headers())
            result_key = f"{operation}Result"
            if result_key not in response:
                raise ArcaClientError("ARCA devolvio una respuesta incompleta.")
            result = response[result_key]
            self._raise_wsfe_errors(operation, result)
            return result

        @staticmethod
        def _raise_wsfe_errors(operation: str, result: dict):
            if operation == "FECAESolicitar" and result.get("FeDetResp"):
                detail = result["FeDetResp"].get("FECAEDetResponse")
                if isinstance(detail, (tuple, list)):
                    detail = detail[0]
                if isinstance(detail, dict) and detail.get("Observaciones") and detail.get("Resultado") != "A":
                    result["Errors"] = {"Err": detail["Observaciones"].get("Obs")}
            errors = result.get("Errors") if isinstance(result, dict) else None
            if not errors:
                return
            error = errors.get("Err")
            if isinstance(error, (tuple, list)):
                error = error[0] if error else {}
            if isinstance(error, dict):
                raise ArcaClientError(f"({error.get('Code', 'ARCA')}) {error.get('Msg', 'Solicitud rechazada')}")
            raise ArcaClientError("ARCA rechazo la solicitud.")

    class TimeoutAfip(Afip):
        def __init__(self, afip_options: dict):
            super().__init__(afip_options)
            self.ElectronicBilling = TimeoutElectronicBilling(self)

        def _headers(self) -> dict[str, str]:
            headers = {
                "Content-Type": "application/json",
                "sdk-version-number": self.sdk_version_number,
                "sdk-library": "python",
                "sdk-environment": self.environment,
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            return headers

        def getServiceTA(self, service: str, force: bool = False) -> dict:
            payload = {
                "environment": self.environment,
                "tax_id": self.CUIT,
                "wsid": service,
                "force_create": force,
                "cert": self.cert,
                "key": self.key,
            }
            return transport.request("POST", "/api/v1/afip/auth", payload, self._headers())

    return TimeoutAfip(
        {
            "CUIT": int(options.cuit),
            "cert": options.credentials.certificate,
            "key": options.credentials.private_key,
            "access_token": options.credentials.access_token,
            "production": production,
        }
    )
