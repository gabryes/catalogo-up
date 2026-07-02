# api.py
# Netlify Function escrita com Flask.
# O Netlify Functions (Python) espera uma função `handler(event, context)`
# que receba o evento HTTP e o contexto de execução da Lambda.
#
# Para rodar o Flask dentro da Lambda, usamos o pacote `serverless-wsgi`,
# que converte o evento do Netlify/AWS Lambda em uma requisição WSGI
# (formato que o Flask entende) e devolve a resposta no formato esperado.

import os
import json
from flask import Flask, jsonify, request
import serverless_wsgi

# ---------------------------------------------------------------------------
# Configuração de variáveis de ambiente
# ---------------------------------------------------------------------------
# As credenciais do Mercado Livre (ML) são lidas do ambiente do Netlify.
# No painel do Netlify, configure em:
#   Site settings > Environment variables
#
# - ML_CLIENT_ID:     App ID do Mercado Livre
# - ML_CLIENT_SECRET: Secret do app do Mercado Livre
# - ML_REDIRECT_URI:  URL de callback autorizada no app do ML
ML_CLIENT_ID = os.environ.get("ML_CLIENT_ID", "")
ML_CLIENT_SECRET = os.environ.get("ML_CLIENT_SECRET", "")
ML_REDIRECT_URI = os.environ.get("ML_REDIRECT_URI", "")

# ---------------------------------------------------------------------------
# Criação da aplicação Flask
# ---------------------------------------------------------------------------
# O Flask é instanciado uma única vez (reaproveitado entre invocações frias/quentes).
app = Flask(__name__)


@app.route("/api/hello", methods=["GET"])
def hello():
    """Rota de exemplo GET /api/hello.

    Retorna uma mensagem simples e indica se as variáveis de ambiente
    do Mercado Livre estão configuradas (sem expor seus valores).
    """
    return jsonify({
        "message": "Olá do Flask no Netlify Functions!",
        "ml_configured": bool(ML_CLIENT_ID and ML_CLIENT_SECRET and ML_REDIRECT_URI),
        "ml_client_id_set": bool(ML_CLIENT_ID),
        "ml_client_secret_set": bool(ML_CLIENT_SECRET),
        "ml_redirect_uri_set": bool(ML_REDIRECT_URI),
    })


@app.route("/api/health", methods=["GET"])
def health():
    """Rota simples para verificar se a função está saudável."""
    return jsonify({"status": "ok"})


@app.route("/api/env", methods=["GET"])
def env_info():
    """Rota auxiliar que mostra (de forma segura) quais variáveis ML existem.

    Nunca retorna o valor real das credenciais, apenas se estão presentes.
    """
    return jsonify({
        "ML_CLIENT_ID": "configurado" if ML_CLIENT_ID else "ausente",
        "ML_CLIENT_SECRET": "configurado" if ML_CLIENT_SECRET else "ausente",
        "ML_REDIRECT_URI": "configurado" if ML_REDIRECT_URI else "ausente",
    })


# ---------------------------------------------------------------------------
# Handler do Netlify Functions
# ---------------------------------------------------------------------------
# Esta é a função que o Netlify chama para cada requisição HTTP.
# - event:   dicionário com dados da requisição (httpMethod, path, headers, body...)
# - context: contexto da execução Lambda (geralmente não usado aqui)
#
# O `serverless_wsgi.handle_request` adapta esse evento para o Flask e
# retorna a resposta no formato esperado pelo Netlify.
def handler(event, context):
    # Se a Lambda for invocada de forma não-HTTP, responde de forma segura.
    if not event or "httpMethod" not in event:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Evento HTTP inválido"}),
            "headers": {"Content-Type": "application/json"},
        }

    # Encaminha a requisição para o app Flask.
    return serverless_wsgi.handle_request(app, event, context)


# ---------------------------------------------------------------------------
# Execução local (apenas para desenvolvimento/testes fora do Netlify)
# ---------------------------------------------------------------------------
# Permite rodar `python api.py` localmente para testar as rotas.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)