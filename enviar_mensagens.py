import csv
import json
import time
import urllib.request
import urllib.error

PHONE_NUMBER_ID = "1027052917169156"
ACCESS_TOKEN = "EAAVYzU6juSwBRQ7J0z10O3xbAQOo0ZAxZA8IXNyu529OOY8DJZBOlcmkFNG32BiyF2hRzuvpZAYCJhKKA06ahHVPn4qiZC20yMHigH0Y27iTBgZBcXJyty5Py5azfdniokC2U3rTZB00UCZAjtOZCmBKIZCMSwtN8oMBztpQBOyydIoEq7NeZCnyDZCR8Uyv1Bpo5wZDZD"
TEMPLATE_NAME = "marketing_pos_venda"
LANGUAGE_CODE = "pt_BR"
CSV_FILE = "clientes.csv"

API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"


def formatar_numero(numero: str) -> str:
    # Remove tudo que não é dígito e garante código do país 55
    digitos = "".join(c for c in numero if c.isdigit())
    if not digitos.startswith("55"):
        digitos = "55" + digitos
    return digitos


def enviar_mensagem(nome: str, numero: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": TEMPLATE_NAME,
            "language": {"code": LANGUAGE_CODE},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "parameter_name": "nome",
                            "text": nome,
                        }
                    ],
                }
            ],
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return {"ok": True, "response": json.loads(resp.read())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": json.loads(e.read())}


def main():
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        clientes = list(csv.DictReader(f))

    print(f"Enviando para {len(clientes)} cliente(s)...\n")

    sucesso, falha = 0, 0
    for cliente in clientes:
        nome = cliente["nome"].strip()
        numero = formatar_numero(cliente["numero"].strip())

        result = enviar_mensagem(nome, numero)

        if result["ok"]:
            print(f"✓ {nome} ({numero})")
            sucesso += 1
        else:
            erro = result["error"].get("error", {}).get("message", result["error"])
            print(f"✗ {nome} ({numero}) — {erro}")
            falha += 1

        time.sleep(0.5)  # evitar rate limit

    print(f"\nConcluído: {sucesso} enviados, {falha} falhas.")


if __name__ == "__main__":
    main()
