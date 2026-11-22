import os
import requests
from supabase import create_client
from datetime import datetime, date

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_KEY"]
token = os.environ["TELEGRAM_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

supabase = create_client(url, key)
produtos = supabase.table("produtos").select("*").execute().data

hoje = date.today()
criticos = []

for item in produtos:
    data_val = datetime.strptime(item["validade"], "%Y-%m-%d").date()
    dias = (data_val - hoje).days
    
    if dias <= 30:
        if dias < 0:
            tag = f"🔴 VENCIDO há {abs(dias)}d"
        elif dias == 0:
            tag = "🔴 VENCE HOJE"
        elif dias <= 7:
            tag = f"🟠 URGENTE ({dias}d)"
        else:
            tag = f"🟡 ATENÇÃO ({dias}d)"
            
        criticos.append((dias, f"{tag} | *{item['nome']}* (Lote: {item['lote']} | Qtd: {item['quantidade']}) - Val: {data_val.strftime('%d/%m/%Y')}"))

if criticos:
    criticos.sort(key=lambda x: x[0])
    linhas = [texto for _, texto in criticos]
    mensagem = (
        f"🚨 *ALERTA DIÁRIO DE VALIDADE (≤ 30 dias)*\n"
        f"📅 Data: {hoje.strftime('%d/%m/%Y')}\n\n"
        + "\n".join(linhas)
    )
    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"}
    )
