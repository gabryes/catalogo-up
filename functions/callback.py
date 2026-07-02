import json
import os
import logging
import urllib.parse
import requests

# Configuração de logs detalhados
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variáveis de ambiente (definir no Netlify)
MERCADO_LIVRE_CLIENT_ID = os.environ.get("MERCADO_LIVRE_CLIENT_ID", "")
MERCADO_LIVRE_CLIENT_SECRET = os.environ.get("MERCADO_LIVRE_CLIENT_SECRET", "")
MERCADO_LIVRE_REDIRECT_URI = os.environ.get("MERCADO_LIVRE_REDIRECT_URI", "")
MERCADO_LIVRE_TOKEN_URL = os.environ.get(
    "MERCADO_LIVRE_TOKEN_URL",
    "https://api.mercadolibre.com/oauth/token",
)
SUCCESS_REDIRECT_URL = os.environ.get("SUCCESS_REDIRECT_URL", "/sucesso")
ERROR_REDIRECT_URL = os.environ.get("ERROR_REDIRECT_URL", "/erro")
TOKENS_FILE = os.environ.get("TOKENS_FILE", "/tmp/mercadolivre_tokens.json")


def _headers():
    """Retorna headers padrão HTTP."""
    return {"Content-Type": "application/json"}


def _log_event(event):
    """Loga informações relevantes do evento recebido."""
    logger.info("Evento recebido: path=%s", event.get("path"))
    logger.info("HTTP method: %s", event.get("httpMethod"))
    logger.info("Query string: %s", event.get("queryStringParameters"))
    logger.info("Headers: %s", json.dumps(event.get("headers", {}), default=str))


def _redirect(location, status_code=302):
    """Cria resposta HTTP de redirecionamento."""
 logger.info("Redirecionando para: %s (status=%s)", location, status_code)
    return {
        "statusCode": status_code,
        "headers": {
            "Location": location,
            "Cache-Control": "no-store",
        },
        "body": "",
    }


def _json_response(status_code, payload):
    """Cria resposta JSON padronizada."""
    return {
        "statusCode": status_code,
        "headers": _headers(),
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _save_tokens_to_file(tokens):
    """Salva tokens em arquivo local (apenas para ambientes efêmeros)."""
    try:
        with open(TOKENS_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)
        logger.info("Tokens salvos em arquivo: %s", TOKENS_FILE)
        return True
    except Exception as exc:
        logger.error("Falha ao salvar tokens em arquivo: %s", str(exc))
        return False


def _exchange_code_for_tokens(code):
    """Troca o código OAuth por access_token e refresh_token no Mercado Livre."""
    logger.info("Iniciando troca de código por tokens no Mercado Livre.")

    if not MERCADO_LIVRE_CLIENT_ID:
        raise ValueError("MERCADO_LIVRE_CLIENT_ID não configurado.")
    if not MERCADO_LIVRE_CLIENT_SECRET:
        raise ValueError("MERCADO_LIVRE_CLIENT_SECRET não configurado.")
    if not MERCADO_LIVRE_REDIRECT_URI:
        raise ValueError("MERCADO_LIVRE_REDIRECT_URI não configurado.")

    payload = {
        "grant_type": "authorization_code",
        "client_id": MERCADO_LIVRE_CLIENT_ID,
        "client_secret": MERCADO_LIVRE_CLIENT_SECRET,
        "code": code,
        "redirect_uri": MERCADO_LIVRE_REDIRECT_URI,
    }

    logger.info("POST para %s", MERCADO_LIVRE_TOKEN_URL)
    response = requests.post(
        MERCADO_LIVRE_TOKEN_URL,
        data=payload,
        headers={"Accept": "application/json"},
        timeout=30,
    )

    logger.info("Resposta do Mercado Livre: status=%s", response.status_code)
    logger.info("Conteúdo da resposta: %s", response.text)

    if response.status_code != 200:
        raise RuntimeError(
            f"Falha ao obter tokens (HTTP {response.status_code}): {response.text}"
        )

    tokens = response.json()
    if "access_token" not in tokens:
        raise RuntimeError("Resposta não contém access_token.")

    logger.info("Tokens obtidos com sucesso.")
    return tokens


def _build_success_redirect(tokens):
    """Constrói URL de sucesso com parâmetros básicos (não sensíveis)."""
    params = {
        "status": "ok",
        "user_id": tokens.get("user_id", ""),
        "expires_in": tokens.get("expires_in", ""),
    }
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v != ""})
    separator = "&" if "?" in SUCCESS_REDIRECT_URL else "?"
    return f"{SUCCESS_REDIRECT_URL}{separator}{query}" if query else SUCCESS_REDIRECT_URL


def _build_error_redirect(message):
    """Constrói URL de erro com mensagem codificada."""
    params = {"status": "erro", "motivo": message}
    query = urllib.parse.urlencode(params)
    separator = "&" if "?" in ERROR_REDIRECT_URL else "?"
    return f"{ERROR_REDIRECT_URL}{separator}{query}"


def handler(event, context):
    """
    Netlify Function: /callback
    Recebe código OAuth do Mercado Livre, troca por tokens e redireciona.
    """
    try:
        _log_event(event)

        query_params = event.get("queryStringParameters") or {}
        code = query_params.get("code")

        # 2. Valida se código existe
        if not code:
            logger.warning("Código OAuth ausente na query string.")
            return _redirect(_build_error_redirect("codigo_ausente"))

        logger.info("Código OAuth recebido: %s", code[:6] + "..." if len(code) > 6 else code)

        # 3. Troca código por tokens
        try:
            tokens = _exchange_code_for_tokens(code)
        except ValueError as exc:
            logger.error("Erro de configuração: %s", str(exc))
            return _redirect(_build_error_redirect("configuracao_invalida"))
        except requests.exceptions.Timeout:
            logger.error("Timeout ao contatar Mercado Livre.")
            return _redirect(_build_error_redirect("timeout"))
        except requests.exceptions.ConnectionError as exc:
            logger.error("Erro de conexão: %s", str(exc))
            return _redirect(_build_error_redirect("erro_conexao"))
        except requests.exceptions.RequestException as exc:
            logger.error("Erro na requisição: %s", str(exc))
            return _redirect(_build_error_redirect("erro_requisicao"))
        except RuntimeError as exc:
            logger.error("Erro ao trocar código: %s", str(exc))
            return _redirect(_build_error_redirect("troca_codigo_falhou"))

        # 4. Salva tokens em arquivo (quando possível) e retorna JSON em log
        saved = _save_tokens_to_file(tokens)
        logger.info("Tokens persistidos em arquivo: %s", saved)
        logger.info("Tokens JSON: %s", json.dumps(tokens, ensure_ascii=False))

        # 5. Redireciona para página de sucesso
        return _redirect(_build_success_redirect(tokens))

    except Exception as exc:
        # 6. Tratamento de todos os erros não previstos
        logger.exception("Erro inesperado no handler: %s", str(exc))
        return _redirect(_build_error_redirect("erro_inesperado"))