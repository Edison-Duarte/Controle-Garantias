import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date

# 1. Configuração da página
st.set_page_config(page_title="Controle de Garantias", layout="wide")

st.title("🛡️ Gestão de Garantias (Google Sheets)")

# 2. Configuração do link (Link que você forneceu)
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1N9KJSTcF6S4Mh7oIdHOmwq4MFkt3M-0TkPZ2VmMqY3Y/edit?usp=sharing"

# 3. Conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        # Lendo a aba "Garantias" (conforme você nomeou)
        # ttl=0 garante que ele busque dados novos sempre que a página recarregar
        return conn.read(spreadsheet=URL_PLANILHA, worksheet="Garantias", ttl=0)
    except Exception as e:
        st.error(f"Erro ao conectar com a planilha: {e}")
        return pd.DataFrame(columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento'])

df = carregar_dados()

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Nova Garantia"):
    with st.form("form_cadastro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nf = c1.text_input("Número da NF")
        item = c2.text_input("Descrição do Item (Ex: Refletor LED)")
        fornecedor = c3.text_input("Fornecedor")
        
        c4, c5 = st.columns(2)
        data_compra = c4.date_input("Data da Compra", value=date.today())
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12)
        
        if st.form_submit_button("Salvar no Google Sheets"):
            if item and nf:
                # Cálculo da data de vencimento
                data_vencimento = pd.to_datetime(data_compra) + pd.DateOffset(months=int(garantia_meses))
                
                # Preparar linha para adicionar
                novo_dado = pd.DataFrame([{
                    "NF": str(nf),
                    "Item": item,
                    "Fornecedor": fornecedor,
                    "data_compra": data_compra.strftime('%Y-%m-%d'),
                    "meses_garantia": int(garantia_meses),
                    "data_vencimento": data_vencimento.strftime('%Y-%m-%d')
                }])
                
                # Combinar com os dados existentes
                df_atualizado = pd.concat([df, novo_dado], ignore_index=True)
                
                # Atualizar a planilha (A aba precisa estar como EDITOR para todos com link)
                conn.update(spreadsheet=URL_PLANILHA, worksheet="Garantias", data=df_atualizado)
                
                st.success("✅ Registro salvo com sucesso na nuvem!")
                st.rerun()
            else:
                st.error("Campos NF e Item são obrigatórios.")

# --- FILTROS E HISTÓRICO ---
st.divider()

if df is not None and not df.empty:
    # Garantir que a coluna de vencimento é data para o cálculo de status
    df['data_vencimento'] = pd.to_datetime(df['data_vencimento'], errors='coerce')
    hoje = pd.to_datetime(date.today())

    def definir_status(dt):
        if pd.isnull(dt): return "❓ SEM DATA"
        diff = (dt - hoje).days
        if diff < 0: return "❌ EXPIRADA"
        elif diff <= 30: return "⚠️ VENCE EM BREVE"
        else: return "✅ ATIVA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    # Filtro de busca
    busca = st.text_input("🔍 Buscar por NF, Item ou Fornecedor").lower()
    
    # Lógica de filtragem
    mask = (
        df['NF'].astype(str).str.lower().str.contains(busca) | 
        df['Item'].astype(str).str.lower().str.contains(busca) | 
        df['Fornecedor'].astype(str).str.lower().str.contains(busca)
    )
    
    df_filtrado = df[mask]

    # Estilização
    def colorir(val):
        color = 'red' if '❌' in val else ('orange' if '⚠️' in val else 'green')
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_filtrado.style.map(colorir, subset=['Status']),
        use_container_width=True
    )
    
    st.caption(f"Total de registros na planilha: {len(df)}")
else:
    st.info("A planilha está vazia ou ainda não foi conectada.")
