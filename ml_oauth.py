import json
import logging
import socketserver
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ============================================================
# Configuração de logging detalhado (compatível com PowerShell)
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ml_oauth")

# ============================================================
# Configurações do App Mercado Livre
# ============================================================
# Preencha com os dados do seu aplicativo criado em:
# https://developers.mercadolivre.com.br/applications/
CLIENT_ID = "4741553669275522"
CLIENT_SECRET = "PtKuYUANhWFT7bBdRYipk7oWrzWD4H2E"
REDIRECT_URI = "http://localhost:8080/callback"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
AUTH_FILE = Path("ml_auth.json")
CALLBACK_PORT = 8080

# Variável global para capturar o código recebido no callback
_received_code = {"code": None, "error": None}


class CallbackHandler(BaseHTTPRequestHandler):
    """Handler do servidor local que recebe o callback do Mercado Livre."""

    def log_message(self, fmt, *args):
        # Redireciona os logs do BaseHTTPRequestHandler para o nosso logger
        log.info("HTTP: " + (fmt % args))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        log.info("Requisição recebida: %s", self.path)

        if parsed.path != "/callback":
            self._respond(404, "Endpoint nao encontrado. Use /callback.")
            return

        if "error" in params:
            _received_code["error"] = params.get("error", ["unknown"])[0]
            error_desc = params.get("error_description", [""])[0]
            log.error("Erro retornado pelo Mercado Livre: %s - %s",
                      _received_code["error"], error_desc)
            self._respond(400, f"Erro de autorizacao: {_received_code['error']}\n{error_desc}")
            return

        if "code" in params:
            _received_code["code"] = params["code"][0]
            log.info("Codigo de autorizacao recebido com sucesso.")
            self._respond(
                200,
                "Autorizacao recebida com sucesso!\n"
                "Voce ja pode fechar esta janela e voltar ao terminal.",
            )
            return

        self._respond(400, "Parametro 'code' ausente na requisicao.")

    def _respond(self, status, message):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(message.encode("utf-8"))


def start_callback_server():
    """Inicia o servidor local na porta 8080 e aguarda o callback."""
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), CallbackHandler)
    server.timeout = 300  # aguarda até 5 minutos
    log.info("Servidor local iniciado em http://127.0.0.1:%d", CALLBACK_PORT)
    return server


def build_auth_url():
    """Monta a URL de autorização do Mercado Livre."""
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def open_browser(url):
    """Abre o navegador no Windows/PowerShell e outros SOs."""
    log.info("Abrindo navegador para autorizacao...")
    log.info("URL de autorizacao: %s", url)
    try:
        opened = webbrowser.open(url, new=2)
        if not opened:
            log.warning("Nao foi possivel abrir o navegador automaticamente.")
            log.warning("Abra manualmente a URL acima no seu navegador.")
        else:
            log.info("Navegador aberto. Aguarde o usuario autorizar o aplicativo.")
    except Exception as exc:
        log.error("Erro ao abrir o navegador: %s", exc)
        log.warning("Abra manualmente a URL acima no seu navegador.")


def wait_for_code(server):
    """Aguarda o callback e retorna o código de autorização."""
    log.info("Aguardando callback do Mercado Livre (timeout: %ds)...", server.timeout)
    handled = False
    while not handled:
        server.handle_request()
        if _received_code["code"] or _received_code["error"]:
            handled = True
    server.server_close()
    log.info("Servidor local encerrado.")

    if _received_code["error"]:
        raise RuntimeError(f"Autorizacao negada: {_received_code['error']}")
    if not _received_code["code"]:
        raise RuntimeError("Codigo de autorizacao nao recebido.")
    return _received_code["code"]


def exchange_code_for_token(code):
    """Troca o código de autorização por access_token e refresh_token."""
    log.info("Trocando codigo de autorizacao por tokens...")

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            log.info("Resposta do token recebida (HTTP %d).", resp.status)
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        log.error("Falha ao obter token (HTTP %d): %s", exc.code, err_body)
        raise RuntimeError(f"Erro ao obter token: {err_body}") from exc
    except urllib.error.URLError as exc:
        log.error("Erro de rede ao obter token: %s", exc)
        raise RuntimeError(f"Erro de rede: {exc}") from exc


def save_tokens(token_data):
    """Salva os tokens em ml_auth.json com metadados."""
    now = datetime.now(timezone.utc)
    payload = {
        "access_token": token_data.get("access_token"),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_in": token_data.get("expires_in"),
        "refresh_token": token_data.get("refresh_token"),
        "scope": token_data.get("scope"),
        "user_id": token_data.get("user_id"),
        "obtained_at": now.isoformat(),
    }

    AUTH_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Tokens salvos em %s", AUTH_FILE.resolve())


def validate_config():
    """Valida que as credenciais foram preenchidas."""
    if CLIENT_ID in (None, "", "SEU_CLIENT_ID"):
        raise RuntimeError("CLIENT_ID nao configurado. Edite o script e informe seu Client ID.")
    if CLIENT_SECRET in (None, "", "SEU_CLIENT_SECRET"):
        raise RuntimeError("CLIENT_SECRET nao configurado. Edite o script e informe seu Client Secret.")


def main():
    """Ponto de entrada principal - executa automaticamente sem argumentos."""
    log.info("=== Iniciando autenticacao OAuth do Mercado Livre ===")

    try:
        validate_config()
    except RuntimeError as exc:
        log.error(str(exc))
        return

    auth_url = build_auth_url()
    server = start_callback_server()

    try:
        open_browser(auth_url)
        code = wait_for_code(server)
        token_data = exchange_code_for_token(code)
        save_tokens(token_data)
        log.info("=== Autenticacao concluida com sucesso! ===")
        log.info("Tokens persistidos em: %s", AUTH_FILE.resolve())
    except Exception as exc:
        log.error("Falha durante a autenticacao: %s", exc)
        try:
            server.server_close()
        except Exception:
            pass
        log.info("=== Autenticacao finalizada com erro ===")


if __name__ == "__main__":
    main()