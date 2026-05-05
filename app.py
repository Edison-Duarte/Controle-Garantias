import streamlit as st
import pandas as pd
from datetime import datetime, date
import os

# Configuração da página
st.set_page_config(page_title="Controle de Garantias - Lâmpadas", layout="wide")

# Função robusta para carregar dados
def carregar_dados():
    colunas = ['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento', 'Status']
    if os.path.exists('garantias.csv'):
        try:
            df = pd.read_csv('garantias.csv')
            df['data_compra'] = pd.to_datetime(df['data_compra'], errors='coerce')
            df['data_vencimento'] = pd.to_datetime(df['data_vencimento'], errors='coerce')
            df = df.dropna(subset=['data_compra', 'data_vencimento'])
            return df
        except Exception:
            return pd.DataFrame(columns=colunas)
    else:
        return pd.DataFrame(columns=colunas)

df = carregar_dados()

# Interface do Usuário
st.title("🛡️ Gestão de Garantias")
st.markdown("Controle de trocas de lâmpadas e refletores.")

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Nova Garantia"):
    with st.form("cadastro_form"):
        c1, c2, c3 = st.columns(3)
        nf = c1.text_input("Número da NF")
        item = c2.text_input("Descrição (ex: Refletor LED 50W)")
        fornecedor = c3.text_input("Fornecedor/Loja")
        
        c4, c5 = st.columns(2)
        data_compra = c4.date_input("Data da Compra", value=date.today())
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12)
        
        if st.form_submit_button("Salvar Registro"):
            data_vencimento = pd.to_datetime(data_compra) + pd.DateOffset(months=garantia_meses)
            
            nova_linha = pd.DataFrame([{
                'NF': str(nf),
                'Item': item,
                'Fornecedor': fornecedor,
                'data_compra': data_compra,
                'meses_garantia': garantia_meses,
                'data_vencimento': data_vencimento
            }])
            
            df = pd.concat([df, nova_linha], ignore_index=True)
            df.to_csv('garantias.csv', index=False)
            st.success("✅ Garantia salva com sucesso!")
            st.rerun()

# --- BUSCA E FILTROS ---
st.divider()
st.subheader("🔍 Pesquisar e Filtrar")

if not df.empty:
    # Atualização de Status em tempo real (essencial para o filtro funcionar)
    hoje = pd.to_datetime(date.today())
    def definir_status(dt_venc):
        diferenca = (dt_venc - hoje).days
        if diferenca < 0:
            return "❌ EXPIRADA"
        elif diferenca <= 30:
            return "⚠️ VENCE EM BREVE"
        else:
            return "✅ ATIVA"

    df['Status'] = df['data_vencimento'].apply(definir_status)

    # Layout de filtros
    col_busca, col_filtro = st.columns([2, 1])
    
    with col_busca:
        termo = st.text_input("Busque por NF, Item ou Fornecedor").strip().lower()
    
    with col_filtro:
        opcoes_status = ["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA"]
        status_selecionados = st.multiselect("Filtrar por Status", options=opcoes_status, default=opcoes_status)

    # Lógica combinada de Filtro (Busca de texto + Status)
    mask_texto = (
        df['NF'].astype(str).str.lower().str.contains(termo) |
        df['Item'].str.lower().str.contains(termo) |
        df['Fornecedor'].str.lower().str.contains(termo)
    )
    
    mask_status = df['Status'].isin(status_selecionados)
    
    df_exibicao = df[mask_texto & mask_status]

    # Estilização da Tabela
    def colorir_status(val):
        if val == "❌ EXPIRADA": color = '#FF4B4B'
        elif val == "⚠️ VENCE EM BREVE": color = '#FFA500'
        else: color = '#008000'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_exibicao.style.map(colorir_status, subset=['Status']),
        use_container_width=True,
        column_config={
            "data_compra": st.column_config.DateColumn("Compra"),
            "data_vencimento": st.column_config.DateColumn("Vencimento"),
            "meses_garantia": "Meses"
        }
    )
    
    st.caption(f"Mostrando {len(df_exibicao)} registros de um total de {len(df)}.")

else:
    st.info("O banco de dados está vazio. Cadastre um item para começar.")
