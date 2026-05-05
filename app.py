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
        # Busca a URL diretamente dos secrets
        url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
        df = conn.read(spreadsheet=url_planilha, worksheet="Garantias", ttl=0)
        
        if df is not None and not df.empty:
            # Remove linhas totalmente vazias
            df = df.dropna(how='all')
            
            # Ajuste de NF e meses para números inteiros (remove o .0)
            for col in ['NF', 'meses_garantia']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
            # TRATAMENTO DE DATAS: Remove o "00:00:00" e converte para formato de data puro
            for col in ['data_compra', 'data_vencimento']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame(columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento'])

df = carregar_dados()

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar Nova Garantia"):
    with st.form("form_cadastro", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nf_input = c1.text_input("Número da NF")
        item = c2.text_input("Descrição do Item")
        fornecedor = c3.text_input("Fornecedor")
        
        c4, c5 = st.columns(2)
        # Input de data padrão Brasil
        data_compra_widget = c4.date_input("Data da Compra", value=date.today(), format="DD/MM/YYYY")
        garantia_meses = c5.number_input("Meses de Garantia", min_value=1, value=12, step=1)
        
        if st.form_submit_button("Salvar Permanentemente"):
            if item and nf_input:
                # Cálculos de data
                dt_compra = pd.to_datetime(data_compra_widget)
                dt_vencimento = dt_compra + pd.DateOffset(months=int(garantia_meses))
                
                # Prepara a nova linha para envio (formato ISO para o Google Sheets entender)
                nova_linha = pd.DataFrame([{
                    "NF": int(nf_input),
                    "Item": item,
                    "Fornecedor": fornecedor,
                    "data_compra": dt_compra.strftime('%Y-%m-%d'),
                    "meses_garantia": int(garantia_meses),
                    "data_vencimento": dt_vencimento.strftime('%Y-%m-%d')
                }])
                
                # Concatena com os dados existentes
                df_atualizado = pd.concat([df, nova_linha], ignore_index=True)
                
                try:
                    url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                    conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_atualizado)
                    st.success("✅ Registro salvo com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar na planilha: {e}")
            else:
                st.error("Por favor, preencha a NF e a Descrição do Item.")

# --- VISUALIZAÇÃO E HISTÓRICO ---
st.divider()

if not df.empty:
    hoje = date.today()

    # Função para definir o status visual baseado na data de vencimento
    def definir_status(dt):
        if pd.isnull(dt) or dt is None: 
            return "⚪ SEM DATA"
        try:
            # Garante comparação entre objetos date
            if isinstance(dt, pd.Timestamp):
                dt = dt.date()
            
            diff = (dt - hoje).days
            if diff < 0: return "❌ EXPIRADA"
            elif diff <= 30: return "⚠️ VENCE EM BREVE"
            else: return "✅ ATIVA"
        except:
            return "⚪ SEM DATA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    # Filtros de busca e status
    col_busca, col_status = st.columns([2, 1])
    busca = col_busca.text_input("🔍 Buscar por NF, Item ou Fornecedor").lower()
    
    status_opcoes = ["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA", "⚪ SEM DATA"]
    status_selecionados = col_status.multiselect("Filtrar por Status", options=status_opcoes, default=status_opcoes)

    # Lógica de filtragem
    mask = (
        (df['NF'].astype(str).str.contains(busca, case=False) | 
         df['Item'].astype(str).str.contains(busca, case=False) | 
         df['Fornecedor'].astype(str).str.contains(busca, case=False)) &
        (df['Status'].isin(status_selecionados))
    )
    
    df_final = df[mask].copy()

    # Estilização das células de status
    def style_status(val):
        if '❌' in str(val): return 'background-color: #ffebee; color: #b71c1c; font-weight: bold'
        if '⚠️' in str(val): return 'background-color: #fff3e0; color: #e65100; font-weight: bold'
        if '✅' in str(val): return 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold'
        return ''

    # Exibição da Tabela de Histórico
    st.dataframe(
        df_final.style.map(style_status, subset=['Status']),
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
    st.caption(f"Exibindo {len(df_final)} registros encontrados.")
else:
    st.info("A planilha está vazia ou ainda não foi carregada.")
