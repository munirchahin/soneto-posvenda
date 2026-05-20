from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = "soneto_webhook_2024"
LOG_FILE = "mensagens_recebidas.txt"


def salvar_mensagem(dados: dict):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"[{timestamp}]\n")
        f.write(json.dumps(dados, ensure_ascii=False, indent=2))
        f.write("\n")


def extrair_mensagem(body: dict) -> dict | None:
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return None

        msg = value["messages"][0]
        contato = value["contacts"][0]

        return {
            "nome": contato["profile"]["name"],
            "numero": msg["from"],
            "tipo": msg["type"],
            "texto": msg.get("text", {}).get("body", "(mídia)"),
            "timestamp": msg["timestamp"],
        }
    except (KeyError, IndexError):
        return None


@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    """Meta verifica o webhook com uma chamada GET."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verificado com sucesso!")
        return challenge, 200
    return "Token inválido", 403


@app.route("/webhook", methods=["POST"])
def receber_mensagem():
    """Recebe mensagens e respostas dos clientes."""
    body = request.get_json()

    mensagem = extrair_mensagem(body)
    if mensagem:
        print(f"\n📩 Nova mensagem de {mensagem['nome']} ({mensagem['numero']}): {mensagem['texto']}")
        salvar_mensagem(mensagem)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
