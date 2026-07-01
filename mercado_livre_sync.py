"""
Mercado Livre Sync Module
=========================

Módulo para sincronização automática de produtos com a API do Mercado Livre.

SETUP
-----
1. Instale as dependências:

    pip install requests APScheduler python-dotenv

2. Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

    ML_CLIENT_ID=seu_client_id
    ML_CLIENT_SECRET=seu_client_secret
    ML_AFFILIATE_ID=seu_affiliate_id

3. Crie um arquivo `services.json` com a estrutura:

    [
      {
        "id": "produto-1",
        "ml_product_id": "MLB123456789",
        "nome": "Produto Exemplo",
        "ml_preco": null,
        "ml_disponibilidade": null,
        "ml_ultima_sincronizacao": null
      }
    ]

EXEMPLO DE USO
--------------

    from mercado_livre_sync import MercadoLivreSync, iniciar_agendador

    sync = MercadoLivreSync()
    sync.autenticar_oauth()
    sync.sincronizar_todos_produtos()

    # Ou inicie o agendador automático (a cada 6 horas):
    iniciar_agendador()
"""

import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:
    BackgroundScheduler = None
    IntervalTrigger = None

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("mercado_livre_sync.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("MercadoLivreSync")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
ML_API_BASE_URL = "https://api.mercadolibre.com"
ML_AUTH_URL = "https://api.mercadolibre.com/oauth/token"
SERVICES_JSON_PATH = os.getenv("ML_SERVICES_JSON", "services.json")
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
RATE_LIMIT_STATUS = 429
NOT_FOUND_STATUS = 404


class MercadoLivreSync:
    """
    Classe responsável pela sincronização de produtos com a API do Mercado Livre.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        affiliate_id: Optional[str] = None,
        services_json_path: str = SERVICES_JSON_PATH,
    ) -> None:
        self.client_id = client_id or os.getenv("ML_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("ML_CLIENT_SECRET")
        self.affiliate_id = affiliate_id or os.getenv("ML_AFFILIATE_ID")
        self.services_json_path = services_json_path

        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        if not self.client_id or not self.client_secret:
            logger.warning(
                "Credenciais OAuth não encontradas. "
                "Defina ML_CLIENT_ID e ML_CLIENT_SECRET no ambiente."
            )

    # -----------------------------------------------------------------------
    # Autenticação
    # -----------------------------------------------------------------------
    def autenticar_oauth(self) -> str:
        """
        Autentica com as credenciais OAuth do Mercado Livre (client credentials).

        Returns:
            str: Access token obtido.

        Raises:
            RuntimeError: Se a autenticação falhar.
        """
        if not self.client_id or not self.client_secret:
            raise RuntimeError("ML_CLIENT_ID e ML_CLIENT_SECRET são obrigatórios para autenticação.")

        # Reutiliza token se ainda for válido (com margem de 60s)
        if self.access_token and time.time() < self.token_expires_at - 60:
            logger.debug("Token OAuth ainda válido, reutilizando.")
            return self.access_token

        logger.info("Autenticando na API do Mercado Livre via OAuth...")
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            response = self._make_request("POST", ML_AUTH_URL, data=payload, use_json=False)
            data = response.json()
            self.access_token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            self.token_expires_at = time.time() + expires_in
            self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})
            logger.info("Autenticação OAuth realizada com sucesso. Token válido por %s segundos.", expires_in)
            return self.access_token
        except Exception as exc:
            logger.error("Falha na autenticação OAuth: %s", exc)
            raise RuntimeError(f"Falha na autenticação OAuth: {exc}") from exc

    # -----------------------------------------------------------------------
    # Busca de produtos
    # -----------------------------------------------------------------------
    def buscar_produtos(self, categoria: str, limite: int = 50) -> List[Dict[str, Any]]:
        """
        Busca produtos por categoria no Mercado Livre.

        Args:
            categoria: ID ou nome da categoria.
            limite: Número máximo de resultados (default 50).

        Returns:
            Lista de produtos encontrados.
        """
        self.autenticar_oauth()
        url = f"{ML_API_BASE_URL}/sites/MLB/search"
        params = {"category": categoria, "limit": limite}

        logger.info("Buscando produtos da categoria '%s' (limite=%d)...", categoria, limite)
        try:
            response = self._make_request("GET", url, params=params)
            data = response.json()
            results = data.get("results", [])
            logger.info("Foram encontrados %d produtos para a categoria '%s'.", len(results), categoria)
            return results
        except Exception as exc:
            logger.error("Erro ao buscar produtos da categoria '%s': %s", categoria, exc)
            return []

    # -----------------------------------------------------------------------
    # Link de afiliado
    # -----------------------------------------------------------------------
    def gerar_link_afiliado(self, product_id: str) -> Optional[str]:
        """
        Gera um link de afiliado para um produto do Mercado Livre.

        Args:
            product_id: ID do produto (ex: MLB123456789).

        Returns:
            Link de afiliado formatado ou None se não for possível gerar.
        """
        if not self.affiliate_id:
            logger.warning("ML_AFFILIATE_ID não configurado. Retornando link padrão sem afiliação.")
            return f"{ML_API_BASE_URL}/items/{product_id}"

        link = f"https://www.mercadolivre.com.br/sec/{product_id}?matt_word={self.affiliate_id}"
        logger.info("Link de afiliado gerado para o produto %s.", product_id)
        return link

    # -----------------------------------------------------------------------
    # Sincronização de preço
    # -----------------------------------------------------------------------
    def sincronizar_preco(self, product_id: str) -> Optional[float]:
        """
        Obtém o preço atual de um produto no Mercado Livre.

        Args:
            product_id: ID do produto.

        Returns:
            Preço atual ou None se não encontrado.
        """
        self.autenticar_oauth()
        url = f"{ML_API_BASE_URL}/items/{product_id}"

        logger.info("Sincronizando preço do produto %s...", product_id)
        try:
            response = self._make_request("GET", url)
            data = response.json()
            price = data.get("price")
            if price is not None:
                logger.info("Preço do produto %s: R$ %.2f", product_id, float(price))
            return float(price) if price is not None else None
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == NOT_FOUND_STATUS:
                logger.warning("Produto %s não encontrado ao sincronizar preço.", product_id)
            else:
                logger.error("Erro HTTP ao sincronizar preço de %s: %s", product_id, exc)
            return None
        except Exception as exc:
            logger.error("Erro inesperado ao sincronizar preço de %s: %s", product_id, exc)
            return None

    # -----------------------------------------------------------------------
    # Sincronização de disponibilidade
    # -----------------------------------------------------------------------
    def sincronizar_disponibilidade(self, product_id: str) -> Optional[bool]:
        """
        Verifica a disponibilidade (estoque) de um produto no Mercado Livre.

        Args:
            product_id: ID do produto.

        Returns:
            True se disponível, False se indisponível, None se não encontrado.
        """
        self.autenticar_oauth()
        url = f"{ML_API_BASE_URL}/items/{product_id}"

        logger.info("Verificando disponibilidade do produto %s...", product_id)
        try:
            response = self._make_request("GET", url)
            data = response.json()
            available_quantity = data.get("available_quantity", 0)
            status_value = data.get("status", "")
            disponivel = available_quantity > 0 and status_value == "active"
            logger.info(
                "Disponibilidade do produto %s: %s (estoque=%s, status=%s)",
                product_id,
                disponivel,
                available_quantity,
                status_value,
            )
            return disponivel
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == NOT_FOUND_STATUS:
                logger.warning("Produto %s não encontrado ao verificar disponibilidade.", product_id)
            else:
                logger.error("Erro HTTP ao verificar disponibilidade de %s: %s", product_id, exc)
            return None
        except Exception as exc:
            logger.error("Erro inesperado ao verificar disponibilidade de %s: %s", product_id, exc)
            return None

    # -----------------------------------------------------------------------
    # Integração com services.json
    # -----------------------------------------------------------------------
    def _ler_services_json(self) -> List[Dict[str, Any]]:
        """Lê o arquivo services.json e retorna a lista de serviços/produtos."""
        try:
            with open(self.services_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "produtos" in data:
                return data["produtos"]
            logger.warning("Formato inesperado em %s. Esperado lista ou dict com 'produtos'.", self.services_json_path)
            return []
        except FileNotFoundError:
            logger.error("Arquivo %s não encontrado.", self.services_json_path)
            return []
        except json.JSONDecodeError as exc:
            logger.error("Erro ao decodificar JSON de %s: %s", self.services_json_path, exc)
            return []

    def _salvar_services_json(self, produtos: List[Dict[str, Any]]) -> None:
        """Salva a lista atualizada de produtos no arquivo services.json."""
        try:
            with open(self.services_json_path, "w", encoding="utf-8") as f:
                json.dump(produtos, f, ensure_ascii=False, indent=2)
            logger.info("Arquivo %s salvo com sucesso.", self.services_json_path)
        except Exception as exc:
            logger.error("Erro ao salvar %s: %s", self.services_json_path, exc)

    def sincronizar_todos_produtos(self) -> Dict[str, Any]:
        """
        Sincroniza todos os produtos presentes no arquivo services.json.

        Atualiza os campos:
            - ml_preco
            - ml_disponibilidade
            - ml_ultima_sincronizacao

        Returns:
            Dicionário com resumo da sincronização (total, sucessos, falhas).
        """
        logger.info("Iniciando sincronização de todos os produtos...")
        produtos = self._ler_services_json()
        if not produtos:
            logger.warning("Nenhum produto encontrado em %s para sincronizar.", self.services_json_path)
            return {"total": 0, "sucessos": 0, "falhas": 0}

        total = len(produtos)
        sucessos = 0
        falhas = 0
        agora = datetime.now(timezone.utc).isoformat()

        for produto in produtos:
            ml_product_id = produto.get("ml_product_id")
            if not ml_product_id:
                logger.warning("Produto sem ml_product_id: %s. Pulando...", produto.get("id", "sem-id"))
                falhas += 1
                continue

            try:
                preco = self.sincronizar_preco(ml_product_id)
                disponibilidade = self.sincronizar_disponibilidade(ml_product_id)

                if preco is None and disponibilidade is None:
                    logger.warning("Produto %s não pôde ser sincronizado (não encontrado).", ml_product_id)
                    produto["ml_disponibilidade"] = False
                    produto["ml_ultima_sincronizacao"] = agora
                    falhas += 1
                else:
                    produto["ml_preco"] = preco
                    produto["ml_disponibilidade"] = disponibilidade if disponibilidade is not None else False
                    produto["ml_ultima_sincronizacao"] = agora
                    sucessos += 1
                    logger.info(
                        "Produto %s sincronizado: preco=%s, disponibilidade=%s",
                        ml_product_id,
                        preco,
                        produto["ml_disponibilidade"],
                    )
            except Exception as exc:
                logger.error("Erro ao sincronizar produto %s: %s", ml_product_id, exc)
                produto["ml_ultima_sincronizacao"] = agora
                falhas += 1

        self._salvar_services_json(produtos)
        resumo = {"total": total, "sucessos": sucessos, "falhas": falhas}
        logger.info(
            "Sincronização concluída: total=%d, sucessos=%d, falhas=%d",
            total,
            sucessos,
            falhas,
        )
        return resumo

    # -----------------------------------------------------------------------
    # Requisição HTTP com tratamento de erros e retry
    # -----------------------------------------------------------------------
    def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        use_json: bool = True,
    ) -> requests.Response:
        """
        Faz uma requisição HTTP com retry automático para rate limit e erros de conexão.

        Args:
            method: Método HTTP (GET, POST, etc).
            url: URL da requisição.
            params: Parâmetros de query string.
            data: Corpo da requisição.
            use_json: Se True, envia data como JSON; caso contrário, como form data.

        Returns:
            Response object.

        Raises:
            requests.HTTPError: Para erros HTTP não recuperáveis.
            requests.ConnectionError: Para falhas de conexão persistentes.
        """
        last_exception: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if method.upper() == "GET":
                    response = self.session.get(url, params=params, timeout=30)
                elif method.upper() == "POST":
                    if use_json:
                        response = self.session.post(url, json=data, params=params, timeout=30)
                    else:
                        response = self.session.post(url, data=data, params=params, timeout=30)
                else:
                    response = self.session.request(method, url, params=params, json=data, timeout=30)

                # Rate limit - aguarda e tenta novamente
                if response.status_code == RATE_LIMIT_STATUS:
                    retry_after = int(response.headers.get("Retry-After", RETRY_DELAY_SECONDS))
                    logger.warning(
                        "Rate limit atingido (tentativa %d/%d). Aguardando %d segundos...",
                        attempt,
                        MAX_RETRIES,
                        retry_after,
                    )
                    time.sleep(retry_after)
                    continue

                # Produto não encontrado - não tenta novamente
                if response.status_code == NOT_FOUND_STATUS:
                    logger.warning("Recurso não encontrado: %s", url)
                    response.raise_for_status()
                    return response

                # Outros erros HTTP
                if response.status_code >= 400:
                    logger.warning(
                        "Erro HTTP %d na tentativa %d/%d para %s",
                        response.status_code,
                        attempt,
                        MAX_RETRIES,
                        url,
                    )
                    response.raise_for_status()

                return response

            except requests.ConnectionError as exc:
                last_exception = exc
                logger.warning(
                    "Falha de conexão (tentativa %d/%d): %s. Aguardando %d segundos...",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    RETRY_DELAY_SECONDS,
                )
                time.sleep(RETRY_DELAY_SECONDS)
            except requests.HTTPError as exc:
                # Erros HTTP não recuperáveis (exceto rate limit já tratado)
                raise exc
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "Erro inesperado (tentativa %d/%d): %s. Aguardando %d segundos...",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    RETRY_DELAY_SECONDS,
                )
                time.sleep(RETRY_DELAY_SECONDS)

        # Esgotou tentativas
        if isinstance(last_exception, requests.ConnectionError):
            logger.error("Falha de conexão persistente após %d tentativas: %s", MAX_RETRIES, url)
            raise last_exception
        raise RuntimeError(f"Falha após {MAX_RETRIES} tentativas para {url}: {last_exception}")


# ---------------------------------------------------------------------------
# Agendamento
# ---------------------------------------------------------------------------
def iniciar_agendador(intervalo_horas: int = 6) -> Optional[BackgroundScheduler]:
    """
    Inicia um agendador em background que sincroniza todos os produtos
    a cada `intervalo_horas` horas (default: 6 horas).

    Args:
        intervalo_horas: Intervalo em horas entre sincronizações.

    Returns:
        Instância do scheduler ou None se APScheduler não estiver instalado.
    """
    if BackgroundScheduler is None or IntervalTrigger is None:
        logger.error("APScheduler não está instalado. Execute: pip install APScheduler")
        return None

    sync = MercadoLivreSync()

    def job() -> None:
        logger.info("=== Iniciando sincronização agendada ===")
        try:
            sync.autenticar_oauth()
            sync.sincronizar_todos_produtos()
        except Exception as exc:
            logger.error("Erro na sincronização agendada: %s", exc)
        logger.info("=== Sincronização agendada finalizada ===")

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=job,
        trigger=IntervalTrigger(hours=intervalo_horas),
        id="mercado_livre_sync_job",
        name=f"Sincronização Mercado Livre (a cada {intervalo_horas}h)",
        replace_existing=True,
    )

    # Executa imediatamente na primeira vez
    scheduler.add_job(
        func=job,
        id="mercado_livre_sync_job_initial",
        name="Sincronização inicial",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Agendador iniciado. Sincronização a cada %d horas.", intervalo_horas)
    return scheduler


def parar_agendador(scheduler: BackgroundScheduler) -> None:
    """Encerra o agendador gracefully."""
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Agendador encerrado.")


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Mercado Livre Sync - Exemplo de Uso ===")
    print()
    print("1. Sincronização única:")
    print("   sync = MercadoLivreSync()")
    print("   sync.autenticar_oauth()")
    print("   sync.sincronizar_todos_produtos()")
    print()
    print("2. Sincronização agendada (a cada 6 horas):")
    print("   scheduler = iniciar_agendador()")
    print("   # ... aplicação roda ...")
    print("   parar_agendador(scheduler)")
    print()
    print("3. Buscar produtos por categoria:")
    print("   produtos = sync.buscar_produtos('MLB1055', limite=10)")
    print()
    print("4. Gerar link de afiliado:")
    print("   link = sync.gerar_link_afiliado('MLB123456789')")
    print()
    print("Execute este módulo com --run para sincronizar imediatamente.")

    import sys
    if "--run" in sys.argv:
        sync = MercadoLivreSync()
        sync.autenticar_oauth()
        resumo = sync.sincronizar_todos_produtos()
        print(f"Resumo: {resumo}")