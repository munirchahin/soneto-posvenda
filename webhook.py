from flask import Flask, request, jsonify, render_template_string
import json
import os
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = "soneto_webhook_2024"
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1027052917169156")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")
DB_FILE = "mensagens.db"


# ── Banco de dados ──────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL,
            nome TEXT NOT NULL,
            texto TEXT NOT NULL,
            direcao TEXT NOT NULL,  -- 'recebida' ou 'enviada'
            timestamp INTEGER NOT NULL,
            lida INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def salvar_mensagem(numero, nome, texto, direcao, timestamp=None):
    if timestamp is None:
        timestamp = int(datetime.now().timestamp())
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO mensagens (numero, nome, texto, direcao, timestamp) VALUES (?, ?, ?, ?, ?)",
        (numero, nome, texto, direcao, timestamp)
    )
    conn.commit()
    conn.close()


def get_contatos():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT numero, nome,
               MAX(timestamp) as ultimo_ts,
               (SELECT texto FROM mensagens m2 WHERE m2.numero = m.numero ORDER BY timestamp DESC LIMIT 1) as ultima_msg,
               SUM(CASE WHEN lida = 0 AND direcao = 'recebida' THEN 1 ELSE 0 END) as nao_lidas
        FROM mensagens m
        GROUP BY numero
        ORDER BY ultimo_ts DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversa(numero):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM mensagens WHERE numero = ? ORDER BY timestamp ASC", (numero,)
    ).fetchall()
    conn.execute("UPDATE mensagens SET lida = 1 WHERE numero = ? AND direcao = 'recebida'", (numero,))
    conn.commit()
    conn.close()
    return [dict(r) for r in rows]


# ── WhatsApp API ────────────────────────────────────────────────────────────

def enviar_whatsapp(numero, texto):
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages",
        data=payload,
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return {"ok": True}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": json.loads(e.read())}


# ── Interface Web ───────────────────────────────────────────────────────────

HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Soneto — WhatsApp</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #111b21; color: #e9edef; height: 100vh; display: flex; }

  /* Sidebar */
  #sidebar { width: 360px; min-width: 360px; background: #111b21; border-right: 1px solid #222d34; display: flex; flex-direction: column; }
  #sidebar-header { background: #202c33; padding: 10px 16px; display: flex; align-items: center; gap: 12px; height: 60px; }
  #sidebar-header h1 { font-size: 19px; font-weight: 600; color: #e9edef; flex: 1; }
  #sidebar-header span { font-size: 11px; color: #8696a0; }
  #contatos { flex: 1; overflow-y: auto; }
  .contato { padding: 12px 16px; display: flex; align-items: center; gap: 12px; cursor: pointer; border-bottom: 1px solid #222d34; transition: background 0.1s; }
  .contato:hover { background: #202c33; }
  .contato.ativo { background: #2a3942; }
  .avatar { width: 48px; height: 48px; border-radius: 50%; background: #00a884; display: flex; align-items: center; justify-content: center; font-size: 20px; font-weight: 600; color: #fff; flex-shrink: 0; }
  .contato-info { flex: 1; min-width: 0; }
  .contato-nome { font-size: 15px; font-weight: 500; color: #e9edef; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .contato-preview { font-size: 13px; color: #8696a0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
  .badge { background: #00a884; color: #fff; border-radius: 50%; width: 20px; height: 20px; font-size: 11px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }

  /* Chat */
  #chat { flex: 1; display: flex; flex-direction: column; background: #0b141a; }
  #chat-vazio { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #8696a0; gap: 16px; }
  #chat-vazio svg { opacity: 0.3; }
  #chat-header { background: #202c33; padding: 10px 16px; display: flex; align-items: center; gap: 12px; height: 60px; }
  #chat-header .avatar { width: 40px; height: 40px; font-size: 16px; }
  #chat-header .nome { font-size: 15px; font-weight: 600; }
  #chat-header .numero { font-size: 13px; color: #8696a0; }
  #mensagens { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 4px; background-image: url("data:image/svg+xml,%3Csvg width='400' height='400' xmlns='http://www.w3.org/2000/svg'%3E%3C/svg%3E"); }
  .msg-wrap { display: flex; }
  .msg-wrap.enviada { justify-content: flex-end; }
  .msg-wrap.recebida { justify-content: flex-start; }
  .msg { max-width: 65%; padding: 7px 12px 6px; border-radius: 8px; font-size: 14px; line-height: 1.4; position: relative; }
  .msg-wrap.enviada .msg { background: #005c4b; border-radius: 8px 0 8px 8px; }
  .msg-wrap.recebida .msg { background: #202c33; border-radius: 0 8px 8px 8px; }
  .msg-hora { font-size: 11px; color: #8696a0; text-align: right; margin-top: 2px; }
  .msg-data { text-align: center; color: #8696a0; font-size: 12px; margin: 12px 0; background: #182229; padding: 4px 12px; border-radius: 8px; align-self: center; }
  #input-area { background: #202c33; padding: 10px 16px; display: flex; align-items: center; gap: 12px; }
  #input-msg { flex: 1; background: #2a3942; border: none; border-radius: 8px; padding: 10px 14px; color: #e9edef; font-size: 15px; outline: none; resize: none; max-height: 120px; }
  #input-msg::placeholder { color: #8696a0; }
  #btn-enviar { background: #00a884; border: none; border-radius: 50%; width: 44px; height: 44px; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background 0.2s; }
  #btn-enviar:hover { background: #00cf9d; }
  #btn-enviar svg { fill: #fff; }

  /* Scroll */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #374045; border-radius: 3px; }
</style>
</head>
<body>

<div id="sidebar">
  <div id="sidebar-header">
    <div class="avatar" style="width:40px;height:40px;font-size:16px;">S</div>
    <h1>Soneto</h1>
    <span id="total-contatos">0 conversas</span>
  </div>
  <div id="contatos"></div>
</div>

<div id="chat">
  <div id="chat-vazio">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 212 212" width="200"><path fill="#364147" d="M106.07 0C47.6 0 0 47.6 0 106.07c0 58.46 47.6 106.06 106.07 106.06 58.46 0 106.06-47.6 106.06-106.06C212.13 47.6 164.53 0 106.07 0zm0 196.13c-49.67 0-90.06-40.4-90.06-90.06 0-49.67 40.4-90.07 90.06-90.07 49.67 0 90.07 40.4 90.07 90.07 0 49.66-40.4 90.06-90.07 90.06z"/></svg>
    <p>Selecione uma conversa</p>
  </div>
</div>

<script>
let numeroAtivo = null;
let pollingInterval = null;

function iniciais(nome) {
  return nome.split(' ').map(p => p[0]).join('').toUpperCase().slice(0, 2);
}

function formatarHora(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
}

function formatarData(ts) {
  const d = new Date(ts * 1000);
  const hoje = new Date();
  const ontem = new Date(hoje - 86400000);
  if (d.toDateString() === hoje.toDateString()) return 'Hoje';
  if (d.toDateString() === ontem.toDateString()) return 'Ontem';
  return d.toLocaleDateString('pt-BR');
}

async function carregarContatos() {
  const res = await fetch('/api/contatos');
  const contatos = await res.json();
  document.getElementById('total-contatos').textContent = contatos.length + ' conversa' + (contatos.length !== 1 ? 's' : '');
  const el = document.getElementById('contatos');
  el.innerHTML = '';
  contatos.forEach(c => {
    const div = document.createElement('div');
    div.className = 'contato' + (c.numero === numeroAtivo ? ' ativo' : '');
    div.innerHTML = `
      <div class="avatar">${iniciais(c.nome)}</div>
      <div class="contato-info">
        <div class="contato-nome">${c.nome}</div>
        <div class="contato-preview">${c.ultima_msg || ''}</div>
      </div>
      ${c.nao_lidas > 0 ? `<div class="badge">${c.nao_lidas}</div>` : ''}
    `;
    div.onclick = () => abrirConversa(c.numero, c.nome);
    el.appendChild(div);
  });
}

async function abrirConversa(numero, nome) {
  numeroAtivo = numero;
  await carregarContatos();

  const res = await fetch('/api/conversa/' + numero);
  const msgs = await res.json();

  document.getElementById('chat').innerHTML = `
    <div id="chat-header">
      <div class="avatar">${iniciais(nome)}</div>
      <div>
        <div class="nome">${nome}</div>
        <div class="numero">+${numero}</div>
      </div>
    </div>
    <div id="mensagens"></div>
    <div id="input-area">
      <textarea id="input-msg" placeholder="Digite uma mensagem" rows="1" onkeydown="teclaEnter(event)"></textarea>
      <button id="btn-enviar" onclick="enviarMensagem()">
        <svg viewBox="0 0 24 24" width="24" height="24"><path d="M1.101 21.757L23.8 12.028 1.101 2.3l.011 7.912 13.623 1.816-13.623 1.817-.011 7.912z"/></svg>
      </button>
    </div>
  `;

  renderizarMensagens(msgs);

  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(() => atualizarMensagens(numero, nome), 3000);
}

function renderizarMensagens(msgs) {
  const el = document.getElementById('mensagens');
  if (!el) return;
  let ultimaData = null;
  el.innerHTML = '';
  msgs.forEach(m => {
    const data = formatarData(m.timestamp);
    if (data !== ultimaData) {
      const sep = document.createElement('div');
      sep.className = 'msg-data';
      sep.textContent = data;
      el.appendChild(sep);
      ultimaData = data;
    }
    const wrap = document.createElement('div');
    wrap.className = 'msg-wrap ' + m.direcao;
    wrap.innerHTML = `
      <div class="msg">
        ${m.texto}
        <div class="msg-hora">${formatarHora(m.timestamp)}</div>
      </div>
    `;
    el.appendChild(wrap);
  });
  el.scrollTop = el.scrollHeight;
}

async function atualizarMensagens(numero, nome) {
  if (numeroAtivo !== numero) return;
  const res = await fetch('/api/conversa/' + numero);
  const msgs = await res.json();
  renderizarMensagens(msgs);
  carregarContatos();
}

function teclaEnter(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    enviarMensagem();
  }
}

async function enviarMensagem() {
  const input = document.getElementById('input-msg');
  const texto = input.value.trim();
  if (!texto || !numeroAtivo) return;
  input.value = '';
  const res = await fetch('/api/enviar', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({numero: numeroAtivo, texto})
  });
  const data = await res.json();
  if (data.ok) atualizarMensagens(numeroAtivo, '');
}

carregarContatos();
setInterval(carregarContatos, 5000);
</script>
</body>
</html>
"""


# ── Rotas ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/contatos")
def api_contatos():
    return jsonify(get_contatos())


@app.route("/api/conversa/<numero>")
def api_conversa(numero):
    return jsonify(get_conversa(numero))


@app.route("/api/enviar", methods=["POST"])
def api_enviar():
    data = request.get_json()
    numero = data.get("numero")
    texto = data.get("texto")
    if not numero or not texto:
        return jsonify({"ok": False, "error": "numero e texto obrigatórios"}), 400
    resultado = enviar_whatsapp(numero, texto)
    if resultado["ok"]:
        salvar_mensagem(numero, "Soneto", texto, "enviada")
    return jsonify(resultado)


@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verificado com sucesso!")
        return challenge, 200
    return "Token inválido", 403


@app.route("/webhook", methods=["POST"])
def receber_mensagem():
    body = request.get_json()
    try:
        entry = body["entry"][0]
        value = entry["changes"][0]["value"]
        if "messages" in value:
            msg = value["messages"][0]
            contato = value["contacts"][0]
            nome = contato["profile"]["name"]
            numero = msg["from"]
            texto = msg.get("text", {}).get("body", "(mídia)")
            timestamp = int(msg["timestamp"])
            salvar_mensagem(numero, nome, texto, "recebida", timestamp)
            print(f"📩 {nome} ({numero}): {texto}")
    except (KeyError, IndexError):
        pass
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


init_db()
