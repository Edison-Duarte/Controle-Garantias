import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date

# 1. Configuração da página
st.set_page_config(page_title="Controle de Garantias", layout="wide")

st.title("🛡️ Gestão de Garantias (Itens por NF)")

# 2. Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
        df = conn.read(spreadsheet=url_planilha, worksheet="Garantias", ttl=0)
        if df is not None and not df.empty:
            df = df.dropna(how='all')
            for col in ['NF', 'meses_garantia']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            for col in ['data_compra', 'data_vencimento']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
    except Exception as e:
        return pd.DataFrame(columns=['NF', 'Item', 'Fornecedor', 'data_compra', 'meses_garantia', 'data_vencimento'])

df_existente = carregar_dados()

# --- ESTADO DA SESSÃO PARA MÚLTIPLOS ITENS ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar NF com Múltiplos Itens", expanded=True):
    # Cabeçalho da NF (Comum para todos os itens)
    c1, c2, c3 = st.columns([1, 1, 2])
    nf_comum = c1.text_input("Número da NF")
    data_comum = c2.date_input("Data da Compra", value=date.today(), format="DD/MM/YYYY")
    fornecedor_comum = c3.text_input("Fornecedor")

    st.divider()
    st.subheader("Itens da Nota")
    
    # Linha para adicionar novo item à lista temporária
    ca, cb, cc = st.columns([2, 1, 1])
    item_nome = ca.text_input("Descrição do Item (ex: Lâmpada)")
    item_garantia = cb.number_input("Garantia (Meses)", min_value=1, value=12)
    
    if st.button("➕ Adicionar Item à Lista"):
        if item_nome and nf_comum:
            # Calcula vencimento individual do item
            dt_venc = pd.to_datetime(data_comum) + pd.DateOffset(months=int(item_garantia))
            
            # Adiciona à lista na memória
            st.session_state.lista_itens.append({
                "NF": nf_comum,
                "Item": item_nome,
                "Fornecedor": fornecedor_comum,
                "data_compra": data_comum.strftime('%Y-%m-%d'),
                "meses_garantia": int(item_garantia),
                "data_vencimento": dt_venc.strftime('%Y-%m-%d')
            })
            st.toast(f"Item '{item_nome}' adicionado!")
        else:
            st.error("Preencha a NF e o Nome do Item antes de adicionar.")

    # Exibe tabela temporária do que será salvo
    if st.session_state.lista_itens:
        st.write("---")
        st.write("**Itens prontos para salvar:**")
        df_temp = pd.DataFrame(st.session_state.lista_itens)
        st.table(df_temp[['Item', 'meses_garantia']])
        
        col_btn1, col_btn2 = st.columns(2)
        
        if col_btn1.button("🗑️ Limpar Lista"):
            st.session_state.lista_itens = []
            st.rerun()

        if col_btn2.button("💾 SALVAR TUDO NO GOOGLE SHEETS", type="primary"):
            try:
                # Junta o novo lote com o que já existe na planilha
                df_novos = pd.DataFrame(st.session_state.lista_itens)
                df_final = pd.concat([df_existente, df_novos], ignore_index=True)
                
                url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_final)
                
                st.success(f"✅ {len(df_novos)} itens salvos com sucesso!")
                st.session_state.lista_itens = [] # Limpa a lista após salvar
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# --- VISUALIZAÇÃO E HISTÓRICO ---
st.divider()
df = carregar_dados() # Recarrega para mostrar o que acabou de ser salvo

if not df.empty:
    hoje = date.today()

    def definir_status(dt):
        if pd.isnull(dt) or dt is None: return "⚪ SEM DATA"
        try:
            if isinstance(dt, pd.Timestamp): dt = dt.date()
            diff = (dt - hoje).days
            if diff < 0: return "❌ EXPIRADA"
            elif diff <= 30: return "⚠️ VENCE"
            else: return "✅ ATIVA"
        except: return "⚪ SEM DATA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    # Filtros
    c_busca, c_status = st.columns([2, 1])
    busca = c_busca.text_input("🔍 Buscar (NF, Item ou Fornecedor)").lower()
    status_selecionados = c_status.multiselect("Status", 
                                             options=["✅ ATIVA", "⚠️ VENCE", "❌ EXPIRADA", "⚪ SEM DATA"], 
                                             default=["✅ ATIVA", "⚠️ VENCE", "❌ EXPIRADA", "⚪ SEM DATA"])

    mask = (
        (df['NF'].astype(str).str.contains(busca, case=False) | 
         df['Item'].astype(str).str.contains(busca, case=False) | 
         df['Fornecedor'].astype(str).str.contains(busca, case=False)) &
        (df['Status'].isin(status_selecionados))
    )
    
    st.dataframe(
        df[mask],
        use_container_width=True,
        hide_index=True,
        column_config={
            "data_compra": st.column_config.DateColumn("Compra", format="DD/MM/YYYY"),
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
        }
    )
