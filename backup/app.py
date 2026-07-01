import os
import logging
import requests
from flask import Flask, request, redirect, jsonify, render_template_string
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração de logs detalhados
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("app")

app = Flask(__name__)

# Variáveis de ambiente obrigatórias
ML_CLIENT_ID = os.getenv("ML_CLIENT_ID")
ML_CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET")
ML_REDIRECT_URI = os.getenv("ML_REDIRECT_URI")

# Verificação se variáveis obrigatórias estão configuradas
REQUIRED_VARS = {
    "ML_CLIENT_ID": ML_CLIENT_ID,
    "ML_CLIENT_SECRET": ML_CLIENT_SECRET,
    "ML_REDIRECT_URI": ML_REDIRECT_URI,
}
missing = [name for name, value in REQUIRED_VARS.items() if not value]
if missing:
    logger.error("Variáveis de ambiente obrigatórias não configuradas: %s", ", ".join(missing))
    raise RuntimeError(
        "As seguintes variáveis de ambiente obrigatórias não estão configuradas: "
        + ", ".join(missing)
    )

logger.info("Variáveis de ambiente carregadas com sucesso.")
logger.info("ML_CLIENT_ID: %s", ML_CLIENT_ID)
logger.info("ML_REDIRECT_URI: %s", ML_REDIRECT_URI)

ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


def _save_tokens(access_token, refresh_token, expires_in, user_id=None):
    """Salva os tokens recebidos do Mercado Livre."""
    logger.info("Salvando tokens recebidos...")
    logger.info("access_token presente: %s", bool(access_token))
    logger.info("refresh_token presente: %s", bool(refresh_token))
    logger.info("expires_in: %s", expires_in)
    logger.info("user_id: %s", user_id)

    try:
        token_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "user_id": user_id,
        }
        # Aqui os tokens podem ser persistidos em banco, arquivo, etc.
        logger.info("Tokens salvos com sucesso: %s", {k: ("***" if k in ("access_token", "refresh_token") else v) for k, v in token_data.items()})
        return True
    except Exception as e:
        logger.exception("Erro ao salvar tokens: %s", e)
        return False


def _exchange_code_for_tokens(code):
    """Troca o código de autorização pelos tokens de acesso."""
    logger.info("Iniciando troca do código de autorização por tokens...")
    logger.info("code: %s", code)

    payload = {
        "grant_type": "authorization_code",
        "client_id": ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
        "code": code,
        "redirect_uri": ML_REDIRECT_URI,
    }

    try:
        logger.info("Enviando requisição para %s", ML_TOKEN_URL)
        response = requests.post(ML_TOKEN_URL, data=payload, timeout=30)
        logger.info("Status da resposta: %s", response.status_code)
        logger.info("Conteúdo da resposta: %s", response.text)

        if response.status_code == 200:
            token_data = response.json()
            logger.info("Tokens obtidos com sucesso.")
            return token_data
        else:
            logger.error("Falha ao obter tokens. Status: %s", response.status_code)
            logger.error("Resposta: %s", response.text)
            return None
    except requests.exceptions.Timeout:
        logger.exception("Timeout ao tentar trocar o código por tokens.")
        return None
    except requests.exceptions.RequestException as e:
        logger.exception("Erro de requisição ao trocar código por tokens: %s", e)
        return None
    except Exception as e:
        logger.exception("Erro inesperado ao trocar código por tokens: %s", e)
        return None


@app.route("/callback")
def callback():
    """Endpoint de callback do OAuth do Mercado Livre."""
    logger.info("Recebida requisição em /callback")
    logger.info("Query params: %s", dict(request.args))

    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        logger.error("Callback recebido com erro: %s", error)
        return redirect("/error?reason=oauth_error")

    if not code:
        logger.error("Callback sem parâmetro 'code'.")
        return redirect("/error?reason=missing_code")

    logger.info("Código de autorização recebido: %s", code)
    logger.info("State recebido: %s", state)

    token_data = _exchange_code_for_tokens(code)
    if not token_data:
        logger.error("Não foi possível obter os tokens.")
        return redirect("/error?reason=token_exchange_failed")

    saved = _save_tokens(
        access_token=token_data.get("access_token"),
        refresh_token=token_data.get("refresh_token"),
        expires_in=token_data.get("expires_in"),
        user_id=token_data.get("user_id"),
    )

    if not saved:
        logger.error("Falha ao salvar os tokens.")
        return redirect("/error?reason=token_save_failed")

    logger.info("Fluxo de OAuth concluído com sucesso.")
    return redirect("/success")


@app.route("/success")
def success():
    """Tela de sucesso após autorização."""
    logger.info("Requisição em /success")
    return render_template_string(
        """
        <!doctype html>
        <html lang="pt-br">
        <head><meta charset="utf-8"><title>Sucesso</title></head>
        <body>
            <h1>Autorização concluída com sucesso!</h1>
            <p>Os tokens foram obtidos e salvos corretamente.</p>
        </body>
        </html>
        """
    )


@app.route("/error")
def error():
    """Tela de erro do fluxo de OAuth."""
    reason = request.args.get("reason", "unknown")
    logger.error("Requisição em /error | reason=%s", reason)
    return render_template_string(
        """
        <!doctype html>
        <html lang="pt-br">
        <head><meta charset="utf-8"><title>Erro</title></head>
        <body>
            <h1>Ocorreu um erro</h1>
            <p>Motivo: {{ reason }}</p>
        </body>
        </html>
        """,
        reason=reason,
    )


@app.errorhandler(404)
def not_found(e):
    logger.warning("Rota não encontrada: %s %s", request.method, request.path)
    return jsonify({"error": "not_found", "message": "Rota não encontrada."}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    logger.warning("Método não permitido: %s %s", request.method, request.path)
    return jsonify({"error": "method_not_allowed", "message": "Método não permitido."}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Erro interno do servidor: %s", e)
    return jsonify({"error": "internal_server_error", "message": "Erro interno do servidor."}), 500


@app.errorhandler(Exception)
def unhandled_exception(e):
    logger.exception("Exceção não tratada: %s", e)
    return jsonify({"error": "unhandled_exception", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info("Iniciando aplicação na porta %s", port)
    app.run(host="0.0.0.0", port=port)