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
            # Tratamento de erro na conversão de datas (evita o ValueError)
            df['data_compra'] = pd.to_datetime(df['data_compra'], errors='coerce')
            df['data_vencimento'] = pd.to_datetime(df['data_vencimento'], errors='coerce')
            # Remove linhas que ficaram com data inválida
            df = df.dropna(subset=['data_compra', 'data_vencimento'])
            return df
        except Exception:
            return pd.DataFrame(columns=colunas)
    else:
        return pd.DataFrame(columns=colunas)

df = carregar_dados()

# Interface do Usuário
st.title("🛡️ Gestão de Garantias")
st.markdown("Controle de trocas de lâmpadas e refletores para evitar compras desnecessárias.")

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
            # Cálculo automático da data de vencimento
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

# --- BUSCA E VISUALIZAÇÃO ---
st.divider()
st.subheader("🔍 Pesquisar Garantias")

if not df.empty:
    # Campo de busca única para múltiplos critérios
    termo = st.text_input("Busque por Nota Fiscal, Nome do Item ou Fornecedor").strip().lower()

    # Atualização de Status em tempo real
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

    # Lógica do Filtro
    if termo:
        mask = (
            df['NF'].astype(str).str.lower().str.contains(termo) |
            df['Item'].str.lower().str.contains(termo) |
            df['Fornecedor'].str.lower().str.contains(termo)
        )
        df_exibicao = df[mask]
    else:
        df_exibicao = df

    # Estilização da Tabela
    def colorir_status(val):
        if val == "❌ EXPIRADA": color = '#FF4B4B' # Vermelho
        elif val == "⚠️ VENCE EM BREVE": color = '#FFA500' # Laranja
        else: color = '#008000' # Verde
        return f'color: {color}; font-weight: bold'

    # Exibição da tabela com correção do .map()
    st.dataframe(
        df_exibicao.style.map(colorir_status, subset=['Status']),
        use_container_width=True,
        column_config={
            "data_compra": st.column_config.DateColumn("Compra"),
            "data_vencimento": st.column_config.DateColumn("Vencimento da Garantia"),
            "meses_garantia": "Meses"
        }
    )
    
    st.caption(f"Exibindo {len(df_exibicao)} registros.")

else:
    st.info("O banco de dados está vazio. Cadastre o primeiro item acima.")
