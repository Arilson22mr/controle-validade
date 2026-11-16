import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, date

st.set_page_config(page_title="Controle de Validade", page_icon="📅", layout="wide")

# --- 1. BARREIRA DE SEGURANÇA (LOGIN SIMPLES) ---
def verificar_senha():
    if st.session_state.get("autenticado", False):
        return True

    st.title("🔒 Acesso Restrito")
    st.markdown("Digite a senha da loja para acessar o painel de estoque.")
    
    senha_digitada = st.text_input("Senha de acesso", type="password")
    
    if st.button("Entrar"):
        if senha_digitada == st.secrets["SENHA_ACESSO"]:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta. Tente novamente.")
            
    return False

if not verificar_senha():
    st.stop()

# ==============================================================================
# DAQUI PARA BAIXO O CÓDIGO SÓ RODA SE A SENHA ESTIVER CORRETA
# ==============================================================================

# --- 2. CONEXÃO COM O SUPABASE (NUVEM) ---
@st.cache_resource
def iniciar_conexao():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = iniciar_conexao()

def adicionar_produto(nome, lote, qtd, validade):
    dados = {
        "nome": nome,
        "lote": lote,
        "quantidade": qtd,
        "validade": validade.strftime("%Y-%m-%d")
    }
    supabase.table("produtos").insert(dados).execute()

def listar_produtos():
    resposta = supabase.table("produtos").select("*").execute()
    return resposta.data

def remover_produto(produto_id):
    supabase.table("produtos").delete().eq("id", produto_id).execute()

# --- 3. INTERFACE VISUAL ---
col_titulo, col_sair = st.columns([5, 1])
col_titulo.title("📅 Gestor de Estoque e Validade")
if col_sair.button("Sair 🔒"):
    st.session_state["autenticado"] = False
    st.rerun()

with st.expander("➕ Cadastrar Novo Lote", expanded=True):
    col1, col2, col3, col4 = st.columns(4)
    nome = col1.text_input("Nome do Produto")
    lote = col2.text_input("Lote")
    qtd = col3.number_input("Quantidade", min_value=1, value=1)
    validade = col4.date_input("Data de Validade", min_value=date.today())
    
    if st.button("Salvar Produto"):
        if nome.strip():
            adicionar_produto(nome, lote, qtd, validade)
            st.success(f"'{nome}' salvo na nuvem!")
            st.rerun()
        else:
            st.error("Por favor, preencha o nome do produto.")

# --- 4. LÓGICA DE PROCESSAMENTO E ALERTAS ---
produtos_salvos = listar_produtos()
hoje = date.today()
dados_processados = []

for item in produtos_salvos:
    data_val = datetime.strptime(item["validade"], "%Y-%m-%d").date()
    dias_restantes = (data_val - hoje).days
    
    if dias_restantes < 0:
        status = "🔴 VENCIDO"
    elif dias_restantes <= 7:
        status = "🟠 URGENTE (Promoção)"
    elif dias_restantes <= 30:
        status = "🟡 ATENÇÃO (Vence este mês)"
    else:
        status = "🟢 OK"
        
    dados_processados.append({
        "ID": item["id"],
        "Status": status,
        "Produto": item["nome"],
        "Lote": item["lote"],
        "Qtd": item["quantidade"],
        "Validade": data_val.strftime("%d/%m/%Y"),
        "Dias Restantes": dias_restantes
    })

st.divider()

if dados_processados:
    df = pd.DataFrame(dados_processados).sort_values(by="Dias Restantes")
    
    st.subheader("Visão Geral do Estoque (Ordenado por Urgência)")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # --- 5. ÁREA PARA DAR BAIXA (EXCLUIR) ---
    st.subheader("🗑️ Dar Baixa em Produto (Vendido / Descartado)")
    col_del1, col_del2 = st.columns([3, 1])
    
    opcoes_exclusao = {f"ID {row['ID']} - {row['Produto']} (Lote: {row['Lote']})": row['ID'] for _, row in df.iterrows()}
    selecionado = col_del1.selectbox("Selecione o lote para remover:", list(opcoes_exclusao.keys()))
    
    if col_del2.button("Remover do Estoque"):
        remover_produto(opcoes_exclusao[selecionado])
        st.warning("Produto removido com sucesso!")
        st.rerun()
else:
    st.info("Nenhum produto cadastrado ainda. Use o formulário acima para adicionar o primeiro lote.")
