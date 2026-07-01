import atexit
import logging
from datetime import datetime, timezone
from threading import Lock

from flask import Flask, jsonify, request

from mercado_livre_sync import MercadoLivreSync, iniciar_agendador, parar_agendador

# ---------------------------------------------------------------------------
# Configuração de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("app_mercado_livre")

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)

# Instância global do sincronizador do Mercado Livre
ml_sync = MercadoLivreSync()

# Lock para evitar sincronizações concorrentes
_sync_lock = Lock()

# Flag para controlar o estado do agendador
_agendador_ativo = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _timestamp_iso() -> str:
    """Retorna o timestamp atual no formato ISO 8601 UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _erro_response(mensagem: str, status: int = 500, detalhe: str = None):
    """Constrói uma resposta JSON de erro padronizada."""
    payload = {
        "status": "erro",
        "mensagem": mensagem,
        "timestamp": _timestamp_iso(),
    }
    if detalhe:
        payload["detalhe"] = detalhe
    logger.error("Resposta de erro %s: %s (%s)", status, mensagem, detalhe or "")
    return jsonify(payload), status


def _iniciar_agendador_seguro():
    """Inicia o agendador de forma segura, evitando duplicidade."""
    global _agendador_ativo
    if _agendador_ativo:
        logger.info("Agendador já está ativo. Nada a fazer.")
        return
    try:
        iniciar_agendador(ml_sync)
        _agendador_ativo = True
        logger.info("Agendador do Mercado Livre iniciado com sucesso.")
    except Exception as exc:
        logger.exception("Falha ao iniciar o agendador do Mercado Livre: %s", exc)


def _parar_agendador_seguro():
    """Para o agendador de forma segura."""
    global _agendador_ativo
    if not _agendador_ativo:
        logger.info("Agendador não está ativo. Nada a fazer.")
        return
    try:
        parar_agendador(ml_sync)
        _agendador_ativo = False
        logger.info("Agendador do Mercado Livre parado com sucesso.")
    except Exception as exc:
        logger.exception("Falha ao parar o agendador do Mercado Livre: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints existentes (compatibilidade)
# ---------------------------------------------------------------------------
@app.route("/api/services", methods=["GET"])
def listar_servicos():
    """Retorna a lista de serviços disponíveis."""
    logger.info("GET /api/services")
    try:
        servicos = [
            {"id": "mercado_livre", "nome": "Mercado Livre", "status": "ativo"},
            {"id": "categorias", "nome": "Categorias", "status": "ativo"},
        ]
        return jsonify({"status": "sucesso", "servicos": servicos}), 200
    except Exception as exc:
        return _erro_response("Erro ao listar serviços", 500, str(exc))


@app.route("/api/categories", methods=["GET"])
def listar_categorias():
    """Retorna a lista de categorias disponíveis."""
    logger.info("GET /api/categories")
    try:
        categorias = ml_sync.obter_categorias() if hasattr(ml_sync, "obter_categorias") else []
        return jsonify({"status": "sucesso", "categorias": categorias}), 200
    except Exception as exc:
        return _erro_response("Erro ao listar categorias", 500, str(exc))


# ---------------------------------------------------------------------------
# Endpoints do Mercado Livre
# ---------------------------------------------------------------------------
@app.route("/api/ml/sync", methods=["GET"])
def sincronizar_ml():
    """Sincroniza todos os produtos manualmente com o Mercado Livre."""
    logger.info("GET /api/ml/sync - Iniciando sincronização manual")

    if not _sync_lock.acquire(blocking=False):
        logger.warning("Sincronização já em andamento. Requisição recusada.")
        return _erro_response(
            "Sincronização já em andamento. Tente novamente mais tarde.",
            status=409,
        )

    try:
        resultado = ml_sync.sincronizar_todos()
        resumo = {
            "total": resultado.get("total", 0),
            "sucessos": resultado.get("sucessos", 0),
            "falhas": resultado.get("falhas", 0),
        }
        logger.info("Sincronização concluída: %s", resumo)
        return jsonify({
            "status": "sucesso",
            "resumo": resumo,
            "timestamp": _timestamp_iso(),
        }), 200
    except Exception as exc:
        logger.exception("Erro durante a sincronização manual: %s", exc)
        return _erro_response("Erro ao sincronizar produtos", 500, str(exc))
    finally:
        _sync_lock.release()


@app.route("/api/ml/status", methods=["GET"])
def status_ml():
    """Retorna o status da última sincronização do Mercado Livre."""
    logger.info("GET /api/ml/status")
    try:
        status = ml_sync.obter_status()
        return jsonify({
            "status": "sucesso",
            "sincronizacao": status,
            "timestamp": _timestamp_iso(),
        }), 200
    except Exception as exc:
        logger.exception("Erro ao obter status: %s", exc)
        return _erro_response("Erro ao obter status da sincronização", 500, str(exc))


@app.route("/api/ml/produtos", methods=["GET"])
def produtos_ml():
    """Retorna todos os produtos com dados do Mercado Livre."""
    logger.info("GET /api/ml/produtos")
    try:
        produtos = ml_sync.obter_produtos()
        return jsonify({
            "status": "sucesso",
            "total": len(produtos) if isinstance(produtos, list) else 0,
            "produtos": produtos,
            "timestamp": _timestamp_iso(),
        }), 200
    except Exception as exc:
        logger.exception("Erro ao obter produtos: %s", exc)
        return _erro_response("Erro ao obter produtos", 500, str(exc))


@app.route("/api/ml/produtos/<categoria>", methods=["GET"])
def produtos_ml_por_categoria(categoria: str):
    """Retorna produtos de uma categoria específica com dados do ML."""
    logger.info("GET /api/ml/produtos/%s", categoria)
    try:
        produtos = ml_sync.obter_produtos(categoria=categoria)
        return jsonify({
            "status": "sucesso",
            "categoria": categoria,
            "total": len(produtos) if isinstance(produtos, list) else 0,
            "produtos": produtos,
            "timestamp": _timestamp_iso(),
        }), 200
    except Exception as exc:
        logger.exception("Erro ao obter produtos da categoria %s: %s", categoria, exc)
        return _erro_response(
            f"Erro ao obter produtos da categoria {categoria}",
            500,
            str(exc),
        )


@app.route("/api/ml/config", methods=["POST"])
def atualizar_config_ml():
    """Atualiza a configuração do Mercado Livre (affiliate_id, etc)."""
    logger.info("POST /api/ml/config")
    try:
        dados = request.get_json(silent=True)
        if not dados:
            return _erro_response("Corpo da requisição inválido ou vazio", 400)

        ml_sync.atualizar_config(dados)
        logger.info("Configuração atualizada: %s", dados)
        return jsonify({
            "status": "sucesso",
            "mensagem": "Configuração atualizada com sucesso",
            "config": dados,
            "timestamp": _timestamp_iso(),
        }), 200
    except ValueError as exc:
        return _erro_response("Dados de configuração inválidos", 400, str(exc))
    except Exception as exc:
        logger.exception("Erro ao atualizar configuração: %s", exc)
        return _erro_response("Erro ao atualizar configuração", 500, str(exc))


# ---------------------------------------------------------------------------
# Tratamento de erros global
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def nao_encontrado(error):
    return _erro_response("Endpoint não encontrado", 404)


@app.errorhandler(405)
def metodo_nao_permitido(error):
    return _erro_response("Método não permitido", 405)


@app.errorhandler(500)
def erro_interno(error):
    return _erro_response("Erro interno do servidor", 500)


# ---------------------------------------------------------------------------
# Ciclo de vida da aplicação
# ---------------------------------------------------------------------------
def _ao_iniciar_app():
    """Rotinas executadas na inicialização da aplicação."""
    logger.info("Inicializando aplicação Flask com integração Mercado Livre.")
    _iniciar_agendador_seguro()


def _ao_encerrar_app():
    """Rotinas executadas no encerramento da aplicação."""
    logger.info("Encerrando aplicação Flask.")
    _parar_agendador_seguro()


# Registra o encerramento do agendador ao finalizar o processo
atexit.register(_ao_encerrar_app)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _ao_iniciar_app()
    try:
        app.run(host="0.0.0.0", port=5000, debug=False)
    finally:
        _ao_encerrar_app()