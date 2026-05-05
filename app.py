import streamlit as st
import pandas as pd
from datetime import datetime, date
import os

# Configuração da página
st.set_page_config(page_title="Controle de Garantias", layout="wide")

def carregar_dados():
    if os.path.exists('garantias.csv'):
        # Carrega garantias e garante que as datas sejam lidas corretamente
        df = pd.read_csv('garantias.csv')
        df['data_compra'] = pd.to_datetime(df['data_compra'])
        df['data_vencimento'] = pd.to_datetime(df['data_vencimento'])
        return df
    else:
        return pd.DataFrame(columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento', 'Status'])

df = carregar_dados()

st.title("🛡️ Gestão de Garantias")

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Novo Item"):
    with st.form("cadastro_form"):
        col1, col2, col3 = st.columns(3)
        nf = col1.text_input("Número da NF")
        item = col2.text_input("Descrição do Item")
        fornecedor = col3.text_input("Fornecedor")
        
        col4, col5 = st.columns(2)
        data_compra = col4.date_input("Data da Compra", value=date.today())
        garantia_meses = col5.number_input("Meses de Garantia", min_value=1, value=12)
        
        if st.form_submit_button("Salvar"):
            data_vencimento = pd.to_datetime(data_compra) + pd.DateOffset(months=garantia_meses)
            nova_linha = pd.DataFrame([{
                'NF': str(nf),
                'Item': item,
                'Fornecedor': fornecedor,
                'data_compra': data_compra,
                'meses_garantia': garantia_meses,
                'data_vencimento': data_vencimento,
                'Status': 'Ativa'
            }])
            df = pd.concat([df, nova_linha], ignore_index=True)
            df.to_csv('garantias.csv', index=False)
            st.success("Cadastrado!")
            st.rerun()

# --- SISTEMA DE FILTROS (BUSCA) ---
st.divider()
st.subheader("🔍 Pesquisar Garantias")

if not df.empty:
    # Barra de busca única para múltiplos campos
    termo_busca = st.text_input("Busque por NF, Nome do Item ou Fornecedor").strip().lower()

    # Lógica de Status
    hoje = pd.to_datetime(date.today())
    df['Status'] = df['data_vencimento'].apply(
        lambda x: "⚠️ VENCE EM BREVE" if 0 < (x - hoje).days <= 30 
        else ("✅ ATIVA" if x > hoje else "❌ EXPIRADA")
    )

    # Aplicação do Filtro de Busca
    if termo_busca:
        # Filtra se o termo estiver na NF, no Item ou no Fornecedor
        mask = (
            df['NF'].astype(str).str.lower().str.contains(termo_busca) |
            df['Item'].str.lower().str.contains(termo_busca) |
            df['Fornecedor'].str.lower().str.contains(termo_busca)
        )
        df_filtrado = df[mask]
    else:
        df_filtrado = df

    # Exibição da Tabela
    def colorir_status(val):
        color = 'red' if 'EXPIRADA' in val else ('orange' if 'BREVE' in val else 'green')
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_filtrado.style.map(colorir_status, subset=['Status']), 
        use_container_width=True
    )
    
    st.caption(f"Mostrando {len(df_filtrado)} de {len(df)} itens registrados.")
else:
    st.info("Nenhum dado encontrado. Cadastre um item para começar.")
