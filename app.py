import streamlit as st
import pandas as pd
import requests
from supabase import create_client
from datetime import datetime, date

st.set_page_config(page_title="ValidadePro | Gestão de Estoque", page_icon="📅", layout="wide")

# --- ESTILO VISUAL LIMPO (ESCONDE MENU TÉCNICO DO STREAMLIT) ---
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM O SUPABASE ---
@st.cache_resource
def iniciar_conexao():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = iniciar_conexao()

# --- 1. LOGIN MULTI-LOJAS ---
def verificar_login():
    if "loja_atual" in st.session_state and st.session_state["loja_atual"] is not None:
        return True

    col_esq, col_centro, col_dir = st.columns([1, 2, 1])
    with col_centro:
        st.title("📅 ValidadePro")
        st.subheader("Acesso ao Painel da Loja")
        senha_digitada = st.text_input("Digite a senha exclusiva da sua loja:", type="password")

        if st.button("Entrar no Sistema", use_container_width=True, type="primary"):
            if senha_digitada.strip():
                res = supabase.table("lojas").select("*").eq("senha", senha_digitada.strip()).execute()
                if res.data:
                    loja = res.data[0]
                    if not loja.get("ativo", True):
                        st.error("Acesso suspenso. Entre em contato com o suporte para regularizar sua assinatura.")
                    else:
                        st.session_state["loja_atual"] = loja
                        st.rerun()
                else:
                    st.error("Senha não encontrada. Verifique e tente novamente.")
            else:
                st.warning("Informe a senha de acesso.")
    return False

if not verificar_login():
    st.stop()

loja = st.session_state["loja_atual"]
LOJA_ID = loja["id"]

# --- 2. FUNÇÕES DO BANCO DE DADOS (ISOLADAS POR LOJA) ---
def listar_produtos():
    res = supabase.table("produtos").select("*").eq("loja_id", LOJA_ID).execute()
    return res.data

def adicionar_produto(nome, lote, qtd, preco_custo, validade):
    supabase.table("produtos").insert({
        "loja_id": LOJA_ID,
        "nome": nome.strip(),
        "lote": lote.strip() if lote else "-",
        "quantidade": int(qtd),
        "preco_custo": float(preco_custo),
        "validade": validade.strftime("%Y-%m-%d")
    }).execute()

def atualizar_produto(prod_id, nome, lote, qtd, preco_custo, validade):
    supabase.table("produtos").update({
        "nome": nome.strip(),
        "lote": lote.strip() if lote else "-",
        "quantidade": int(qtd),
        "preco_custo": float(preco_custo),
        "validade": validade.strftime("%Y-%m-%d")
    }).eq("id", prod_id).eq("loja_id", LOJA_ID).execute()

def remover_produto(prod_id):
    supabase.table("produtos").delete().eq("id", prod_id).eq("loja_id", LOJA_ID).execute()

# --- 3. FUNÇÃO DE ALERTA TELEGRAM (FILTRA <= 30 DIAS) ---
def enviar_resumo_telegram(lista_produtos, chat_id, nome_loja):
    if not chat_id:
        return False, "Esta loja ainda não possui um Chat ID do Telegram configurado."

    hoje = date.today()
    criticos = []
    valor_total_risco = 0.0

    for item in lista_produtos:
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

    if not criticos:
        return False, "Nenhum produto vencido ou faltando 30 dias para vencer."

    criticos.sort(key=lambda x: x[0])
    linhas = [texto for _, texto in criticos]

    resumo_financeiro = f"\n💰 *Capital em risco (≤ 30d): R$ {valor_total_risco:,.2f}*" if valor_total_risco > 0 else ""
    mensagem = (
        f"🚨 *ALERTA DE VALIDADE — {nome_loja.upper()}*\n"
        f"📅 Data: {hoje.strftime('%d/%m/%Y')}{resumo_financeiro}\n\n"
        + "\n".join(linhas)
    )

    token = st.secrets["TELEGRAM_TOKEN"]
    resposta = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": mensagem, "parse_mode": "Markdown"}
    )

    if resposta.status_code == 200:
        return True, f"Resumo com {len(criticos)} item(ns) enviado para o Telegram!"
    return False, f"Erro no Telegram: {resposta.text}"

# --- 4. CABEÇALHO DA LOJA ---
col_tit, col_sair = st.columns([5, 1])
col_tit.title(f"📅 {loja['nome_loja']}")
col_tit.caption("Controle Inteligente de Validade e Prevenção de Perdas")

if col_sair.button("Sair 🔒", use_container_width=True):
    st.session_state["loja_atual"] = None
    st.rerun()

# --- 5. PROCESSAMENTO DOS DADOS ---
produtos_salvos = listar_produtos()
hoje = date.today()
dados_processados = []

qtd_vencidos = 0
qtd_urgentes = 0
qtd_atencao = 0
risco_financeiro_30d = 0.0

for item in produtos_salvos:
    data_val = datetime.strptime(item["validade"], "%Y-%m-%d").date()
    dias_restantes = (data_val - hoje).days
    custo_unit = float(item.get("preco_custo") or 0)
    valor_lote = custo_unit * int(item["quantidade"])

    if dias_restantes < 0:
        status = "🔴 VENCIDO"
        qtd_vencidos += 1
        risco_financeiro_30d += valor_lote
    elif dias_restantes <= 7:
        status = "🟠 URGENTE (≤ 7d)"
        qtd_urgentes += 1
        risco_financeiro_30d += valor_lote
    elif dias_restantes <= 30:
        status = "🟡 ATENÇÃO (≤ 30d)"
        qtd_atencao += 1
        risco_financeiro_30d += valor_lote
    else:
        status = "🟢 OK"

    dados_processados.append({
        "ID": item["id"],
        "Status": status,
        "Produto": item["nome"],
        "Lote": item["lote"],
        "Qtd": int(item["quantidade"]),
        "Custo Unit. (R$)": custo_unit,
        "Total Lote (R$)": valor_lote,
        "Validade": data_val.strftime("%d/%m/%Y"),
        "Validade_ISO": data_val,
        "Dias Restantes": dias_restantes
    })

# --- 6. PAINEL DE INDICADORES (KPIs) NO TOPO ---
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("📦 Total de Lotes", len(dados_processados))
k2.metric("🔴 Vencidos", qtd_vencidos)
k3.metric("🟠 Urgentes (≤ 7d)", qtd_urgentes)
k4.metric("🟡 Atenção (≤ 30d)", qtd_atencao)
k5.metric("💰 Risco (≤ 30d)", f"R$ {risco_financeiro_30d:,.2f}")

st.divider()

# --- 7. CADASTRO DE NOVO LOTE ---
with st.expander("➕ Cadastrar Novo Produto / Lote", expanded=False):
    with st.form("form_cadastro", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1.5, 2])
        nome = c1.text_input("Nome do Produto *")
        lote = c2.text_input("Lote (opcional)")
        qtd = c3.number_input("Qtd *", min_value=1, value=1, step=1)
        preco_custo = c4.number_input("Custo Unit. (R$)", min_value=0.0, value=0.0, step=0.50, format="%.2f")
        validade = c5.date_input("Validade *", value=date.today())

        if st.form_submit_button("💾 Salvar Produto", type="primary"):
            if nome.strip():
                adicionar_produto(nome, lote, qtd, preco_custo, validade)
                st.success(f"'{nome}' cadastrado com sucesso!")
                st.rerun()
            else:
                st.error("Preencha o nome do produto.")

# --- 8. TABELA, BUSCA, FILTROS E EXPORTAÇÃO ---
if dados_processados:
    df = pd.DataFrame(dados_processados).sort_values(by="Dias Restantes")

    # Barra de ações superiores (Telegram + Exportar CSV)
    col_acao1, col_acao2 = st.columns([3, 1])
    with col_acao1:
        if st.button("📲 Enviar Alerta Crítico (≤ 30 dias) no Telegram", use_container_width=True):
            ok, msg = enviar_resumo_telegram(produtos_salvos, loja.get("telegram_chat_id"), loja["nome_loja"])
            if ok:
                st.toast(msg, icon="✅")
                st.success(msg)
            else:
                st.warning(msg)

    with col_acao2:
        df_export = df.drop(columns=["Validade_ISO"])
        csv = df_export.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        st.download_button(
            label="📥 Baixar Planilha (Excel/CSV)",
            data=csv,
            file_name=f"estoque_{loja['nome_loja'].lower().replace(' ', '_')}_{hoje}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # Busca rápida e filtro por status
    col_busca, col_filtro = st.columns([3, 2])
    termo_busca = col_busca.text_input("🔍 Buscar por nome do produto ou lote:", placeholder="Ex: Leite, Lote 42...")
    filtro_status = col_filtro.selectbox(
        "Filtrar por situação:",
        ["Todos", "Apenas Críticos (≤ 30 dias)", "🔴 VENCIDO", "🟠 URGENTE (≤ 7d)", "🟡 ATENÇÃO (≤ 30d)", "🟢 OK"]
    )

    df_filtrado = df.copy()
    if termo_busca.strip():
        mask = (
            df_filtrado["Produto"].str.contains(termo_busca, case=False, na=False) |
            df_filtrado["Lote"].str.contains(termo_busca, case=False, na=False)
        )
        df_filtrado = df_filtrado[mask]

    if filtro_status == "Apenas Críticos (≤ 30 dias)":
        df_filtrado = df_filtrado[df_filtrado["Dias Restantes"] <= 30]
    elif filtro_status != "Todos":
        df_filtrado = df_filtrado[df_filtrado["Status"] == filtro_status]

    # Exibição da tabela formatada
    colunas_visiveis = ["Status", "Produto", "Lote", "Qtd", "Custo Unit. (R$)", "Total Lote (R$)", "Validade", "Dias Restantes"]
    st.dataframe(
        df_filtrado[colunas_visiveis],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Custo Unit. (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
            "Total Lote (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        }
    )

    st.divider()

    # --- 9. EDITAR OU EXCLUIR PRODUTO SALVO ---
    tab_editar, tab_excluir = st.tabs(["✏️ Editar Produto Salvo", "🗑️ Dar Baixa / Excluir Lote"])

    opcoes_itens = {
        f"ID {row['ID']} — {row['Produto']} (Lote: {row['Lote']} | Val: {row['Validade']})": row
        for _, row in df.iterrows()
    }

    with tab_editar:
        item_escolhido_edit = st.selectbox("Selecione o produto que deseja alterar:", list(opcoes_itens.keys()), key="sel_edit")
        dados_item = opcoes_itens[item_escolhido_edit]

        with st.form("form_edicao"):
            e1, e2, e3, e4, e5 = st.columns([3, 2, 1, 1.5, 2])
            novo_nome = e1.text_input("Nome do Produto", value=dados_item["Produto"])
            novo_lote = e2.text_input("Lote", value=dados_item["Lote"])
            nova_qtd = e3.number_input("Quantidade", min_value=1, value=int(dados_item["Qtd"]), step=1)
            novo_custo = e4.number_input("Custo Unit. (R$)", min_value=0.0, value=float(dados_item["Custo Unit. (R$)"]), step=0.50, format="%.2f")
            nova_validade = e5.date_input("Data de Validade", value=dados_item["Validade_ISO"])

            if st.form_submit_button("✅ Salvar Alterações", type="primary"):
                if novo_nome.strip():
                    atualizar_produto(int(dados_item["ID"]), novo_nome, novo_lote, nova_qtd, novo_custo, nova_validade)
                    st.success("Produto atualizado com sucesso!")
                    st.rerun()
                else:
                    st.error("O nome do produto não pode ficar em branco.")

    with tab_excluir:
        col_del1, col_del2 = st.columns([3, 1])
        item_escolhido_del = col_del1.selectbox("Selecione o lote vendido ou descartado:", list(opcoes_itens.keys()), key="sel_del")
        if col_del2.button("🗑️ Remover Definitivamente", use_container_width=True):
            remover_produto(int(opcoes_itens[item_escolhido_del]["ID"]))
            st.warning("Lote removido do estoque!")
            st.rerun()
else:
    st.info("Nenhum produto cadastrado ainda nesta loja. Clique em '➕ Cadastrar Novo Produto / Lote' acima para começar.")
