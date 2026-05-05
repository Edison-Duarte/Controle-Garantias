import streamlit as st
import pandas as pd
from datetime import datetime, date

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Controle de Garantias", layout="wide")

# 2. INICIALIZAÇÃO DA MEMÓRIA (O segredo para o histórico não sumir)
if 'historico_garantias' not in st.session_state:
    st.session_state.historico_garantias = pd.DataFrame(
        columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento', 'Status']
    )

st.title("🛡️ Gestão de Garantias")

# 3. FORMULÁRIO DE CADASTRO
with st.expander("📝 Cadastrar Nova Garantia", expanded=True):
    with st.form("cadastro_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nf = c1.text_input("Número da NF")
        item = c2.text_input("Descrição (Ex: Refletor LED)")
        fornecedor = c3.text_input("Fornecedor")
        
        c4, c5 = st.columns(2)
        data_compra = c4.date_input("Data da Compra", value=date.today())
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12)
        
        submit = st.form_submit_button("Salvar no Histórico")
        
        if submit:
            if nf and item:
                # Cálculo da data de vencimento
                dt_compra_dt = pd.to_datetime(data_compra)
                dt_vencimento = dt_compra_dt + pd.DateOffset(months=garantia_meses)
                
                # Cálculo do Status
                hoje = pd.to_datetime(date.today())
                diferenca = (dt_vencimento - hoje).days
                if diferenca < 0: status = "❌ EXPIRADA"
                elif diferenca <= 30: status = "⚠️ VENCE EM BREVE"
                else: status = "✅ ATIVA"

                # Criar nova linha
                nova_garantia = pd.DataFrame([{
                    'NF': nf,
                    'Item': item,
                    'Fornecedor': fornecedor,
                    'data_compra': data_compra,
                    'meses_garantia': garantia_meses,
                    'data_vencimento': dt_vencimento.date(),
                    'Status': status
                }])
                
                # ADICIONAR AO HISTÓRICO NA MEMÓRIA
                st.session_state.historico_garantias = pd.concat(
                    [st.session_state.historico_garantias, nova_garantia], 
                    ignore_index=True
                )
                st.success(f"Item '{item}' adicionado ao histórico!")
            else:
                st.error("Por favor, preencha a NF e o Nome do Item.")

# 4. EXIBIÇÃO DO HISTÓRICO E BUSCA
st.divider()
st.subheader("🔍 Histórico de Garantias")

df_exibir = st.session_state.historico_garantias

if not df_exibir.empty:
    # Barra de busca
    busca = st.text_input("Pesquisar por NF, Item ou Fornecedor").strip().lower()
    
    if busca:
        mask = (
            df_exibir['NF'].astype(str).str.lower().contains(busca) |
            df_exibir['Item'].str.lower().contains(busca) |
            df_exibir['Fornecedor'].str.lower().contains(busca)
        )
        df_exibir = df_exibir[mask]

    # Estilização
    def style_status(val):
        color = 'red' if '❌' in val else ('orange' if '⚠️' in val else 'green')
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df_exibir.style.map(style_status, subset=['Status']),
        use_container_width=True
    )
    
    # Botão para baixar o que foi cadastrado (Já que a memória limpa ao fechar)
    csv = df_exibir.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Baixar Histórico em CSV",
        data=csv,
        file_name='garantias_cadastradas.csv',
        mime='text/csv',
    )
else:
    st.info("Nenhum item cadastrado nesta sessão.")
