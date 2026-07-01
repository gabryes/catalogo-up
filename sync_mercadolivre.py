#!/usr/bin/env python3
"""
Script para sincronizar produtos do Mercado Livre.

Uso:
    python sync_mercadolivre.py --test-connection
    python sync_mercadolivre.py --run
    python sync_mercadolivre.py --run --category MLB1234 --limit 50
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configurações
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
AUTH_FILE = BASE_DIR / "ml_auth.json"
OUTPUT_FILE = BASE_DIR / "services.json"

ML_API_BASE = "https://api.mercadolibre.com"
ML_AUTH_URL = "https://auth.mercadolivre.com.br/oauth/token"
# Caso o domínio de auth acima não funcione, usamos o genérico como fallback.
ML_AUTH_URL_FALLBACK = "https://api.mercadolibre.com/oauth/token"

TOKEN_EXPIRY_MARGIN_SECONDS = 60  # renova um pouco antes de expirar de fato
HTTP_TIMEOUT = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml_sync")


# ---------------------------------------------------------------------------
# Exceções
# ---------------------------------------------------------------------------


class MLAuthError(Exception):
    """Erro de autenticação/autorização no Mercado Livre."""


class MLAPIError(Exception):
    """Erro genérico de comunicação com a API do Mercado Livre."""


class MLForbiddenError(MLAPIError):
    """Erro 403 - acesso proibido/escopo insuficiente."""


# ---------------------------------------------------------------------------
# Helpers de credenciais
# ---------------------------------------------------------------------------


def load_auth() -> Dict[str, Any]:
    """Carrega credenciais e token persistido em ml_auth.json."""
    if not AUTH_FILE.exists():
        logger.error("Arquivo de credenciais não encontrado: %s", AUTH_FILE)
        raise MLAuthError(f"Arquivo não encontrado: {AUTH_FILE}")

    try:
        with AUTH_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.error("Falha ao ler %s: %s", AUTH_FILE, exc)
        raise MLAuthError(f"JSON inválido em {AUTH_FILE}: {exc}") from exc

    required = ["client_id", "client_secret"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        logger.error("Campos obrigatórios ausentes em ml_auth.json: %s", ", ".join(missing))
        raise MLAuthError(f"Campos ausentes: {', '.join(missing)}")

    if not data.get("access_token"):
        logger.warning("Nenhum access_token presente em ml_auth.json. Será necessário renovar.")

    return data


def save_auth(data: Dict[str, Any]) -> None:
    """Persiste o estado atualizado de credenciais/token em ml_auth.json."""
    try:
        with AUTH_FILE.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        logger.info("Credenciais atualizadas salvas em %s", AUTH_FILE)
    except OSError as exc:
        logger.error("Não foi possível salvar %s: %s", AUTH_FILE, exc)
        raise MLAuthError(f"Erro ao salvar credenciais: {exc}") from exc


def token_is_expired(auth: Dict[str, Any]) -> bool:
    """Verifica se o token atual está expirado (ou próximo de expirar)."""
    expires_at = auth.get("expires_at")
    if not expires_at:
        # Sem informação de expiração: considera expirado para forçar renovação segura.
        return True
    try:
        exp = float(expires_at)
    except (TypeError, ValueError):
        return True
    now = time.time()
    return now >= (exp - TOKEN_EXPIRY_MARGIN_SECONDS)


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


def refresh_token(auth: Dict[str, Any]) -> Dict[str, Any]:
    """Renova o access_token usando refresh_token (fluxo OAuth do ML)."""
    refresh = auth.get("refresh_token")
    if not refresh:
        logger.error("refresh_token ausente. Não é possível renovar automaticamente.")
        raise MLAuthError("refresh_token ausente em ml_auth.json")

    payload = {
        "grant_type": "refresh_token",
        "client_id": auth["client_id"],
        "client_secret": auth["client_secret"],
        "refresh_token": refresh,
    }

    logger.info("Renovando access_token via refresh_token...")
    response = _do_auth_request(payload)

    auth["access_token"] = response["access_token"]
    auth["refresh_token"] = response.get("refresh_token", auth["refresh_token"])
    auth["token_type"] = response.get("token_type", "Bearer")
    auth["scope"] = response.get("scope", auth.get("scope", ""))
    auth["expires_in"] = response.get("expires_in", 21600)
    auth["expires_at"] = time.time() + int(auth["expires_in"])
    auth["updated_at"] = datetime.now(timezone.utc).isoformat()

    save_auth(auth)
    logger.info("Token renovado com sucesso. Expira em %s segundos.", auth["expires_in"])
    return auth


def _do_auth_request(payload: Dict[str, str]) -> Dict[str, Any]:
    """Executa a requisição de OAuth tentando o endpoint principal e o fallback."""
    last_error: Optional[str] = None
    for url in (ML_AUTH_URL, ML_AUTH_URL_FALLBACK):
        try:
            logger.debug("POST %s payload=%s", url, {k: (v if k != "client_secret" else "***") for k, v in payload.items()})
            resp = requests.post(url, data=payload, timeout=HTTP_TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"{url}: {exc}"
            logger.warning("Falha de rede ao chamar %s: %s", url, exc)
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise MLAuthError(f"Resposta OAuth inválida de {url}: {exc}") from exc

        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}

        last_error = f"{url} retornou HTTP {resp.status_code}: {body}"
        logger.warning("Erro OAuth em %s: HTTP %s -> %s", url, resp.status_code, body)

    raise MLAuthError(f"Falha ao renovar token: {last_error}")


def ensure_valid_token(auth: Dict[str, Any]) -> Dict[str, Any]:
    """Garante que o token esteja válido, renovando se necessário."""
    if not auth.get("access_token") or token_is_expired(auth):
        logger.info("Token ausente ou expirado. Iniciando renovação...")
        auth = refresh_token(auth)
    else:
        logger.info("Token atual ainda válido. Seguindo com o token existente.")
    return auth


# ---------------------------------------------------------------------------
# Cliente da API
# ---------------------------------------------------------------------------


def _headers(auth: Dict[str, Any]) -> Dict[str, str]:
    token_type = auth.get("token_type", "Bearer")
    return {
        "Authorization": f"{token_type} {auth['access_token']}",
        "Accept": "application/json",
        "User-Agent": "ml-sync-script/1.0",
    }


def handle_http_error(response: requests.Response, context: str) -> None:
    """Trata erros HTTP com mensagens claras, incluindo 403."""
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    if status == 403:
        message = (
            "Acesso proibido (HTTP 403) ao %s. Possíveis causas:\n"
            " - O access_token não tem escopo/permissão para este recurso.\n"
            " - O usuário não possui acesso à categoria/recurso solicitado.\n"
            " - O token foi revogado ou a aplicação foi desautorizada.\n"
            " - Limite de requisições excedido para este recurso.\n"
            "Detalhes: %s"
        ) % (context, body)
        logger.error(message)
        raise MLForbiddenError(message)

    if status == 401:
        message = f"Não autorizado (HTTP 401) ao {context}. Token inválido ou expirado. Detalhes: {body}"
        logger.error(message)
        raise MLAuthError(message)

    if status == 404:
        message = f"Recurso não encontrado (HTTP 404) ao {context}. Detalhes: {body}"
        logger.error(message)
        raise MLAPIError(message)

    if 500 <= status < 600:
        message = f"Erro no servidor do Mercado Livre (HTTP {status}) ao {context}. Detalhes: {body}"
        logger.error(message)
        raise MLAPIError(message)

    message = f"Erro inesperado (HTTP {status}) ao {context}. Detalhes: {body}"
    logger.error(message)
    raise MLAPIError(message)


def get_user_id(auth: Dict[str, Any]) -> str:
    """Obtém o ID do usuário autenticado (/users/me)."""
    url = f"{ML_API_BASE}/users/me"
    logger.info("Validando conexão: GET %s", url)
    try:
        resp = requests.get(url, headers=_headers(auth), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Falha de rede ao validar conexão: %s", exc)
        raise MLAPIError(f"Falha de rede: {exc}") from exc

    if resp.status_code != 200:
        handle_http_error(resp, "validar conexão (users/me)")

    data = resp.json()
    user_id = str(data.get("id", ""))
    if not user_id:
        raise MLAPIError("Resposta de /users/me não contém id.")
    logger.info("Conexão validada. Usuário: id=%s, nickname=%s", user_id, data.get("nickname"))
    return user_id


def fetch_products_by_category(
    auth: Dict[str, Any],
    user_id: str,
    category: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Busca produtos do usuário, opcionalmente filtrando por categoria.
    Usa o endpoint /users/{id}/items/search com filtros.
    """
    url = f"{ML_API_BASE}/users/{user_id}/items/search"
    params: Dict[str, Any] = {"limit": limit or 50}
    if category:
        params["category"] = category
        logger.info("Buscando produtos da categoria %s (limite=%s)", category, params["limit"])
    else:
        logger.info("Buscando produtos sem filtro de categoria (limite=%s)", params["limit"])

    try:
        resp = requests.get(url, headers=_headers(auth), params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Falha de rede ao buscar produtos: %s", exc)
        raise MLAPIError(f"Falha de rede: {exc}") from exc

    if resp.status_code != 200:
        handle_http_error(resp, "buscar produtos (users/{id}/items/search)")

    data = resp.json()
    item_ids: List[str] = data.get("results", []) or []
    total = data.get("paging", {}).get("total", len(item_ids))
    logger.info("Total encontrado: %s | IDs retornados: %s", total, len(item_ids))

    if limit is not None:
        item_ids = item_ids[:limit]

    products: List[Dict[str, Any]] = []
    for idx, item_id in enumerate(item_ids, start=1):
        logger.info("[%s/%s] Obtendo detalhes do item %s", idx, len(item_ids), item_id)
        product = fetch_product_detail(auth, item_id)
        if product:
            products.append(product)
        # Pequeno delay para evitar rate-limit
        time.sleep(0.1)

    return products


def fetch_product_detail(auth: Dict[str, Any], item_id: str) -> Optional[Dict[str, Any]]:
    """Obtém detalhes de um item pelo ID."""
    url = f"{ML_API_BASE}/items/{item_id}"
    try:
        resp = requests.get(url, headers=_headers(auth), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("Falha de rede ao obter item %s: %s", item_id, exc)
        return None

    if resp.status_code == 404:
        logger.warning("Item %s não encontrado (404). Pulando.", item_id)
        return None

    if resp.status_code != 200:
        try:
            handle_http_error(resp, f"obter item {item_id}")
        except MLForbiddenError:
            # Em 403 em item individual, logamos e pulamos para não abortar tudo.
            return None
    
    return resp.json()


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------


def save_products(products: List[Dict[str, Any]], category: Optional[str]) -> None:
    """Salva os produtos sincronizados em services.json."""
    payload = {
        "source": "mercadolivre",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "count": len(products),
        "products": products,
    }
    try:
        with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        logger.info("Produtos salvos em %s (%s registros).", OUTPUT_FILE, len(products))
    except OSError as exc:
        logger.error("Falha ao salvar %s: %s", OUTPUT_FILE, exc)
        raise


# ---------------------------------------------------------------------------
# Operações CLI
# ---------------------------------------------------------------------------


def op_test_connection() -> int:
    """Valida a conexão com o Mercado Livre."""
    logger.info("=== TESTE DE CONEXÃO ===")
    try:
        auth = load_auth()
        auth = ensure_valid_token(auth)
        user_id = get_user_id(auth)
        logger.info("SUCESSO: conexão validada para o usuário %s.", user_id)
        return 0
    except MLForbiddenError as exc:
        logger.error("FALHA 403 no teste de conexão: %s", exc)
        return 3
    except MLAuthError as exc:
        logger.error("FALHA de autenticação no teste de conexão: %s", exc)
        return 2
    except MLAPIError as exc:
        logger.error("FALHA de API no teste de conexão: %s", exc)
        return 4
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro inesperado no teste de conexão: %s", exc)
        return 1


def op_run(category: Optional[str], limit: Optional[int]) -> int:
    """Executa a sincronização de produtos."""
    logger.info("=== SINCRONIZAÇÃO DE PRODUTOS ===")
    if category:
        logger.info("Categoria: %s", category)
    if limit is not None:
        logger.info("Limite: %s", limit)

    try:
        auth = load_auth()
        auth = ensure_valid_token(auth)
        user_id = get_user_id(auth)
        products = fetch_products_by_category(auth, user_id, category=category, limit=limit)
        logger.info("Sincronização concluída. Produtos obtidos: %s", len(products))
        save_products(products, category)
        return 0
    except MLForbiddenError as exc:
        logger.error("FALHA 403 durante a sincronização: %s", exc)
        logger.error("Verifique permissões/escopos do token e se a categoria é acessível.")
        return 3
    except MLAuthError as exc:
        logger.error("FALHA de autenticação durante a sincronização: %s", exc)
        return 2
    except MLAPIError as exc:
        logger.error("FALHA de API durante a sincronização: %s", exc)
        return 4
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro inesperado durante a sincronização: %s", exc)
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sincroniza produtos do Mercado Livre com suporte a OAuth e renovação de token.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--test-connection",
        action="store_true",
        help="Valida a conexão com o Mercado Livre (não sincroniza produtos).",
    )
    group.add_argument(
        "--run",
        action="store_true",
        help="Executa a sincronização de produtos.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Categoria do Mercado Livre para filtrar (ex.: MLB1234).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Quantidade máxima de produtos a sincronizar.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Habilita logs de nível DEBUG.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Logs DEBUG habilitados.")

    if args.test_connection:
        return op_test_connection()

    if args.run:
        if args.limit is not None and args.limit <= 0:
            logger.error("--limit deve ser um número positivo.")
            return 1
        return op_run(category=args.category, limit=args.limit)

    # Não deve chegar aqui por causa do grupo mutuamente exclusivo required.
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())