import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="Controle de Garantias", layout="wide")

st.title("🛡️ Gestão de Garantias (Google Sheets)")

# --- CONFIGURAÇÃO DA CONEXÃO ---
# Substitua pelo link que você copiou no Passo 1
URL_PLANILHA = "COLE_AQUI_O_LINK_DA_SUA_PLANILHA"

conn = st.connection("gsheets", type=GSheetsConnection)

# Função para carregar dados da planilha
def carregar_dados():
    return conn.read(spreadsheet=URL_PLANILHA, worksheet="garantias")

df = carregar_dados()

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Nova Garantia"):
    with st.form("form_cadastro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nf = c1.text_input("Número da NF")
        item = c2.text_input("Descrição do Item")
        fornecedor = c3.text_input("Fornecedor")
        
        c4, c5 = st.columns(2)
        data_compra = c4.date_input("Data da Compra", value=date.today())
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12)
        
        if st.form_submit_button("Salvar Permanentemente"):
            if item and nf:
                # Cálculo da data de vencimento
                data_vencimento = pd.to_datetime(data_compra) + pd.DateOffset(months=garantia_meses)
                
                # Novo dado formatado
                novo_dado = pd.DataFrame([{
                    "NF": str(nf),
                    "Item": item,
                    "Fornecedor": fornecedor,
                    "data_compra": data_compra.strftime('%Y-%m-%d'),
                    "meses_garantia": int(garantia_meses),
                    "data_vencimento": data_vencimento.strftime('%Y-%m-%d')
                }])
                
                # Junta com os dados existentes e atualiza a planilha
                df_atualizado = pd.concat([df, novo_dado], ignore_index=True)
                conn.update(spreadsheet=URL_PLANILHA, worksheet="garantias", data=df_atualizado)
                
                st.success("✅ Salvo no Google Sheets!")
                st.rerun()
            else:
                st.error("Preencha os campos obrigatórios (NF e Item).")

# --- FILTROS E HISTÓRICO ---
st.divider()
if not df.empty:
    # Lógica de Status
    hoje = pd.to_datetime(date.today())
    df['data_vencimento'] = pd.to_datetime(df['data_vencimento'])
    
    def definir_status(dt):
        diff = (dt - hoje).days
        if diff < 0: return "❌ EXPIRADA"
        elif diff <= 30: return "⚠️ VENCE EM BREVE"
        else: return "✅ ATIVA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    # Filtros
    c_busca, c_status = st.columns([2, 1])
    busca = c_busca.text_input("🔍 Buscar por NF, Item ou Fornecedor").lower()
    status_filtro = c_status.multiselect("Status", 
                                       options=["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA"],
                                       default=["✅ ATIVA", "⚠️ VENCE EM BREVE"])

    # Aplicar filtros
    mask = (
        (df['NF'].astype(str).str.lower().str.contains(busca) | 
         df['Item'].str.lower().str.contains(busca) | 
         df['Fornecedor'].str.lower().str.contains(busca)) & 
        (df['Status'].isin(status_filtro))
    )
    
    # Exibição estilizada
    st.dataframe(
        df[mask].style.map(lambda x: 'color: red; font-weight: bold' if x == "❌ EXPIRADA" else '', subset=['Status']),
        use_container_width=True
    )
else:
    st.info("Nenhum registro encontrado na planilha.")
