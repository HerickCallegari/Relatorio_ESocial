import json
import re
from typing import Any

import httpx

from app.settings import settings

# Chaves do payload cujo VALOR nunca pode aparecer em logs ou mensagens de UI.
_SECRET_PAYLOAD_KEYS = ("chave", "identificacao", "senha", "password")

# Textos (nao-JSON) que o SOC retorna significando "zero registros" — NAO sao erro.
_EMPTY_RESULT_SENTINELS = (
    "nenhum resultado",
    "nenhum registro",
    "sem resultado",
    "nao ha registros",
    "não há registros",
)


class SocClientError(Exception):
    """Erro de comunicacao ou recusa do WebService SOC.

    A mensagem ja e segura para exibir na UI: nao contem URL, parametros
    nem chaves de acesso.
    """


class SocClient:
    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def export_data(self, payload: dict[str, str]) -> list[dict[str, Any]]:
        # Valores sensiveis desta requisicao, para remover de qualquer mensagem.
        secrets = {str(payload[k]) for k in _SECRET_PAYLOAD_KEYS if payload.get(k)}

        try:
            response = httpx.get(
                settings.soc_base_url,
                params={"parametro": json.dumps(payload, ensure_ascii=False)},
                timeout=self.timeout,
            )
        except httpx.HTTPError:
            # NUNCA repassar a excecao original: a URL carrega a chave nos parametros.
            raise SocClientError(
                "Nao foi possivel conectar ao WebService do SOC (falha de rede ou timeout)."
            ) from None

        if response.status_code >= 400:
            # Nao usar raise_for_status(): a mensagem do httpx inclui a URL (com a chave).
            detail = self._clean(response.text, secrets) or f"HTTP {response.status_code}"
            raise SocClientError(
                f"O SOC recusou a requisicao (HTTP {response.status_code}): {detail}"
            )

        return self._parse_response(response.text, secrets)

    def _parse_response(self, text: str, secrets: set[str]) -> list[dict[str, Any]]:
        stripped = (text or "").strip()
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            # SOC devolve texto/HTML: pode ser "zero registros" (sucesso) ou erro real.
            cleaned = self._clean(stripped, secrets)
            if self._is_empty_result(cleaned):
                return []
            detail = cleaned or "resposta vazia"
            raise SocClientError(
                f"O SOC retornou uma resposta inesperada (nao-JSON): {detail}"
            ) from None

        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        if isinstance(data, dict):
            error_message = self._detect_error(data)
            if error_message:
                raise SocClientError(
                    f"O SOC recusou a requisicao: {self._clean(error_message, secrets)}"
                )
            for key in ("data", "dados", "resultado", "retorno"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [data]

        return []

    @staticmethod
    def _is_empty_result(cleaned_text: str) -> bool:
        """True se o texto do SOC indica ausencia de registros (sucesso vazio)."""
        low = cleaned_text.lower()
        return any(sentinel in low for sentinel in _EMPTY_RESULT_SENTINELS)

    @staticmethod
    def _detect_error(data: dict[str, Any]) -> str | None:
        """Retorna a mensagem de erro se o dict aparentar ser uma resposta de erro."""
        falsy = (None, False, "", 0, "false", "False", "0")
        for flag in ("erro", "error", "hasError", "isError"):
            if data.get(flag) in falsy:
                continue
            for msg_key in ("mensagem", "message", "msg", "descricao"):
                msg = data.get(msg_key)
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            return str(data.get(flag))
        return None

    @staticmethod
    def _clean(text: str, secrets: set[str]) -> str:
        """Sanitiza texto para exibicao: remove tags HTML, colapsa espacos,
        remove valores sensiveis e trunca."""
        if not text:
            return ""
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for secret in secrets:
            if secret:
                cleaned = cleaned.replace(secret, "***")
        return cleaned[:300]


soc_client = SocClient()
