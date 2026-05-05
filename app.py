import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date

# 1. Configuração da página
st.set_page_config(page_title="Controle de Garantias", layout="wide")

st.title("🛡️ Gestão de Garantias (Google Sheets)")

# 2. Conexão com Google Sheets (Lê automaticamente dos Secrets)
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        # Busca a URL diretamente dos Secrets para maior segurança
        url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
        
        # Tenta ler a aba "Garantias"
        return conn.read(spreadsheet=url_planilha, worksheet="Garantias", ttl=0)
    except Exception:
        try:
            # Caso a aba "Garantias" não exista, tenta ler a primeira aba disponível
            return conn.read(spreadsheet=url_planilha, ttl=0)
        except Exception as e:
            st.error(f"Erro crítico de conexão: {e}")
            # Retorna DataFrame vazio com as colunas padrão se tudo falhar
            return pd.DataFrame(columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento'])

df = carregar_dados()

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Nova Garantia", expanded=True):
    with st.form("form_cadastro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nf = c1.text_input("Número da NF")
        item = c2.text_input("Descrição do Item (Ex: Refletor LED)")
        fornecedor = c3.text_input("Fornecedor")
        
        c4, c5 = st.columns(2)
        data_compra = c4.date_input("Data da Compra", value=date.today())
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12)
        
        if st.form_submit_button("Salvar Permanentemente"):
            if item and nf:
                # Cálculo da data de vencimento
                dt_compra = pd.to_datetime(data_compra)
                dt_vencimento = dt_compra + pd.DateOffset(months=int(garantia_meses))
                
                # Preparar nova linha
                nova_linha = pd.DataFrame([{
                    "NF": str(nf),
                    "Item": item,
                    "Fornecedor": fornecedor,
                    "data_compra": data_compra.strftime('%Y-%m-%d'),
                    "meses_garantia": int(garantia_meses),
                    "data_vencimento": dt_vencimento.strftime('%Y-%m-%d')
                }])
                
                # Concatenar com dados antigos (removendo linhas totalmente vazias)
                df_limpo = df.dropna(how='all')
                df_atualizado = pd.concat([df_limpo, nova_linha], ignore_index=True)
                
                # Atualizar Planilha usando a URL dos Secrets
                try:
                    url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                    conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_atualizado)
                    st.success("✅ Salvo com sucesso no Google Sheets!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}. Verifique se o e-mail da conta de serviço é EDITOR na planilha.")
            else:
                st.error("Campos NF e Item são obrigatórios.")

# --- VISUALIZAÇÃO E FILTROS ---
st.divider()

# Garantir que o df não é None antes de processar
if df is not None and not df.empty:
    # Tratamento de datas
    df['data_vencimento'] = pd.to_datetime(df['data_vencimento'], errors='coerce')
    hoje = pd.to_datetime(date.today())

    def definir_status(dt):
        if pd.isnull(dt): return "❓ SEM DATA"
        diff = (dt - hoje).days
        if diff < 0: return "❌ EXPIRADA"
        elif diff <= 30: return "⚠️ VENCE EM BREVE"
        else: return "✅ ATIVA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    # Filtros
    col_busca, col_status = st.columns([2, 1])
    busca = col_busca.text_input("🔍 Buscar por NF, Item ou Fornecedor").lower()
    
    status_opcoes = ["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA"]
    status_selecionados = col_status.multiselect("Filtrar Status", options=status_opcoes, default=status_opcoes)

    # Aplicar filtros
    mask = (
        (df['NF'].astype(str).str.lower().str.contains(busca) | 
         df['Item'].astype(str).str.lower().str.contains(busca) | 
         df['Fornecedor'].astype(str).str.lower().str.contains(busca)) &
        (df['Status'].isin(status_selecionados))
    )
    
    df_final = df[mask]

    # Estilização
    def style_status(val):
        if '❌' in str(val): return 'color: #ff4b4b; font-weight: bold'
        if '⚠️' in str(val): return 'color: #ffa500; font-weight: bold'
        if '✅' in str(val): return 'color: #008000; font-weight: bold'
        return ''

    st.dataframe(
        df_final.style.map(style_status, subset=['Status']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "data_compra": "Data Compra",
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "meses_garantia": "Garantia (Meses)"
        }
    )
    
    st.caption(f"Mostrando {len(df_final)} de {len(df)} registros.")
else:
    st.info("A base de dados está vazia ou não foi encontrada. Cadastre o primeiro item acima.")
