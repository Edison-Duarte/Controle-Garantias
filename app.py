import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date

# 1. Configuração da página
st.set_page_config(page_title="Controle de Garantias", layout="wide")

st.title("🛡️ Gestão de Garantias (Google Sheets)")

# 2. Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
        df = conn.read(spreadsheet=url_planilha, worksheet="Garantias", ttl=0)
        
        if df is not None and not df.empty:
            # Limpa linhas totalmente vazias que as vezes ficam no Sheets
            df = df.dropna(how='all')
            
            # Ajuste 1: NF e meses_garantia como INTEIROS (sem .0)
            for col in ['NF', 'meses_garantia']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
            # Ajuste 2: Tratar datas (forçando formato datetime para cálculo)
            df['data_compra'] = pd.to_datetime(df['data_compra'], errors='coerce')
            df['data_vencimento'] = pd.to_datetime(df['data_vencimento'], errors='coerce')
            
        return df
    except Exception as e:
        st.error(f"Erro ao carregar: {e}")
        return pd.DataFrame(columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento'])

df = carregar_dados()

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Nova Garantia", expanded=False):
    with st.form("form_cadastro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nf_input = c1.text_input("Número da NF")
        item = c2.text_input("Descrição do Item")
        fornecedor = c3.text_input("Fornecedor")
        
        c4, c5 = st.columns(2)
        data_compra_input = c4.date_input("Data da Compra", value=date.today(), format="DD/MM/YYYY")
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12, step=1)
        
        if st.form_submit_button("Salvar Permanentemente"):
            if item and nf_input:
                dt_compra = pd.to_datetime(data_compra_input)
                dt_vencimento = dt_compra + pd.DateOffset(months=int(garantia_meses))
                
                nova_linha = pd.DataFrame([{
                    "NF": int(nf_input),
                    "Item": item,
                    "Fornecedor": fornecedor,
                    "data_compra": dt_compra.strftime('%Y-%m-%d'),
                    "meses_garantia": int(garantia_meses),
                    "data_vencimento": dt_vencimento.strftime('%Y-%m-%d')
                }])
                
                df_atualizado = pd.concat([df, nova_linha], ignore_index=True)
                
                try:
                    url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                    conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_atualizado)
                    st.success("✅ Salvo com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
            else:
                st.error("Campos NF e Item são obrigatórios.")

# --- VISUALIZAÇÃO E FILTROS ---
st.divider()

if not df.empty:
    hoje = pd.to_datetime(date.today())

    # Função de status robusta para lidar com datas vazias (Nat)
    def definir_status(dt):
        if pd.isnull(dt): return "⚪ SEM DATA"
        diff = (dt - hoje).days
        if diff < 0: return "❌ EXPIRADA"
        elif diff <= 30: return "⚠️ VENCE EM BREVE"
        else: return "✅ ATIVA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    col_busca, col_status = st.columns([2, 1])
    busca = col_busca.text_input("🔍 Buscar por NF, Item ou Fornecedor").lower()
    
    status_opcoes = ["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA", "⚪ SEM DATA"]
    status_selecionados = col_status.multiselect("Filtrar Status", options=status_opcoes, default=status_opcoes)

    # Filtro que aceita valores nulos sem quebrar
    mask = (
        (df['NF'].astype(str).str.contains(busca, case=False) | 
         df['Item'].astype(str).str.contains(busca, case=False) | 
         df['Fornecedor'].astype(str).str.contains(busca, case=False)) &
        (df['Status'].isin(status_selecionados))
    )
    
    df_final = df[mask]

    def style_status(val):
        if '❌' in str(val): return 'background-color: #ffebee; color: #b71c1c; font-weight: bold'
        if '⚠️' in str(val): return 'background-color: #fff3e0; color: #e65100; font-weight: bold'
        if '✅' in str(val): return 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold'
        return ''

    st.dataframe(
        df_final.style.applymap(style_status, subset=['Status']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "NF": st.column_config.TextColumn("NF"),
            "data_compra": st.column_config.DateColumn("Data Compra", format="DD/MM/YYYY"),
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "meses_garantia": st.column_config.NumberColumn("Garantia (Meses)", format="%d"),
            "Status": "Status da Garantia"
        }
    )
    st.caption(f"Mostrando {len(df_final)} registros.")
else:
    st.info("Nenhum registro encontrado na planilha.")
