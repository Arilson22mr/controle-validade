import os
import requests
from supabase import create_client
from datetime import datetime, date

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_KEY"]
token = os.environ["TELEGRAM_TOKEN"]

supabase = create_client(url, key)

# Busca todas as lojas ativas que tenham Telegram configurado
lojas = supabase.table("lojas").select("*").eq("ativo", True).execute().data
hoje = date.today()

for loja in lojas:
    chat_id = loja.get("telegram_chat_id")
    if not chat_id:
        continue

    produtos = supabase.table("produtos").select("*").eq("loja_id", loja["id"]).execute().data
    criticos = []
    valor_total_risco = 0.0

    for item in produtos:
        data_val = datetime.strptime(item["validade"], "%Y-%m-%d").date()
        dias = (data_val - hoje).days

        if dias <= 30:
            custo_unit = float(item.get("preco_custo") or 0)
            subtotal = custo_unit * int(item["quantidade"])
            valor_total_risco += subtotal

            if dias < 0:
                tag = f"🔴 VENCIDO há {abs(dias)}d"
            elif dias == 0:
                tag = "🔴 VENCE HOJE"
            elif dias <= 7:
                tag = f"🟠 URGENTE ({dias}d)"
            else:
                tag = f"🟡 ATENÇÃO ({dias}d)"

            valor_txt = f" | Risco: R$ {subtotal:,.2f}" if subtotal > 0 else ""
            criticos.append((
                dias,
                f"{tag} | *{item['nome']}* (Lote: {item['lote']} | Qtd: {item['quantidade']}{valor_txt}) - Val: {data_val.strftime('%d/%m/%Y')}"
            ))

    if criticos:
        criticos.sort(key=lambda x: x[0])
        linhas = [texto for _, texto in criticos]
        resumo_fin = f"\n💰 *Capital em risco (≤ 30d): R$ {valor_total_risco:,.2f}*" if valor_total_risco > 0 else ""

        mensagem = (
            f"🚨 *ALERTA DIÁRIO — {loja['nome_loja'].upper()}*\n"
            f"📅 Data: {hoje.strftime('%d/%m/%Y')}{resumo_fin}\n\n"
            + "\n".join(linhas)
        )

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"}
        )
