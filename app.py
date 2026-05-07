import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date

# 1. Configuração da página
st.set_page_config(page_title="Controle de Garantias", layout="wide")

st.title("🛡️ InvoiceSis - Gestão de NF e Garantias")

# 2. Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
        df = conn.read(spreadsheet=url_planilha, worksheet="Garantias", ttl=0)
        if df is not None and not df.empty:
            df = df.dropna(how='all')
            # Ajuste de tipos numéricos
            for col in ['NF', 'meses_garantia', 'quantidade']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            
            # Limpeza de datas
            colunas_data = ['data_emissao', 'data_vencimento']
            for col in colunas_data:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
    except Exception as e:
        return pd.DataFrame(columns=['NF', 'data_emissao', 'Item', 'quantidade', 'Fornecedor', 'meses_garantia', 'data_vencimento'])

df_existente = carregar_dados()

# --- ESTADO DA SESSÃO ---
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# --- FORMULÁRIO DE CADASTRO ---
with st.expander("📝 Cadastrar NF e Lote de Itens", expanded=True):
    # Cabeçalho da NF (Campos comuns)
    c1, c2, c3 = st.columns([1, 1, 2])
    nf_comum = c1.text_input("Número da NF")
    data_emissao_comum = c2.date_input("Data da Emissão", value=date.today(), format="DD/MM/YYYY")
    fornecedor_comum = c3.text_input("Fornecedor")

    st.divider()
    
    # Adição de Itens individuais
    ca, cb, cc = st.columns([2, 1, 1])
    item_nome = ca.text_input("Descrição do Item")
    item_qtd = cb.number_input("Quantidade", min_value=1, value=1)
    item_garantia = cc.number_input("Garantia (Meses)", min_value=1, value=12)
    
    if st.button("➕ Adicionar à Lista"):
        if item_nome and nf_comum:
            # Cálculo do vencimento baseado na Data da Emissão
            dt_emissao = pd.to_datetime(data_emissao_comum)
            dt_venc = dt_emissao + pd.DateOffset(months=int(item_garantia))
            
            st.session_state.lista_itens.append({
                "NF": nf_comum,
                "data_emissao": data_emissao_comum.strftime('%Y-%m-%d'),
                "Item": item_nome,
                "quantidade": int(item_qtd),
                "Fornecedor": fornecedor_comum,
                "meses_garantia": int(item_garantia),
                "data_vencimento": dt_venc.strftime('%Y-%m-%d')
            })
            st.toast(f"Item '{item_nome}' adicionado!")
        else:
            st.error("Preencha o número da NF e a Descrição do Item.")

    # Tabela temporária de itens
    if st.session_state.lista_itens:
        st.write("---")
        df_temp = pd.DataFrame(st.session_state.lista_itens)
        st.dataframe(df_temp[['Item', 'quantidade', 'meses_garantia']], use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("🗑️ Limpar Lista"):
            st.session_state.lista_itens = []
            st.rerun()

        if col_btn2.button("💾 SALVAR", type="primary"):
            try:
                df_novos = pd.DataFrame(st.session_state.lista_itens)
                df_final = pd.concat([df_existente, df_novos], ignore_index=True)
                url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_final)
                st.success("✅ Salvo com sucesso!")
                st.session_state.lista_itens = []
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# --- HISTÓRICO COM FILTROS (ATUALIZADO) ---
st.divider()
df = carregar_dados()

if not df.empty:
    hoje = date.today()

    def definir_status(dt):
        if pd.isnull(dt) or dt is None: return "⚪ SEM DATA"
        try:
            if isinstance(dt, pd.Timestamp): dt = dt.date()
            diff = (dt - hoje).days
            if diff < 0: return "❌ EXPIRADA"
            elif diff <= 30: return "⚠️ VENCE EM BREVE"
            else: return "✅ ATIVA"
        except: return "⚪ SEM DATA"
    
    df['Status'] = df['data_vencimento'].apply(definir_status)

    c_busca, c_status = st.columns([2, 1])
    busca = c_busca.text_input("🔍 Buscar (NF, Item, Fornecedor)").lower()
    status_opcoes = ["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA", "⚪ SEM DATA"]
    status_selecionados = c_status.multiselect("Filtrar por Status", options=status_opcoes, default=status_opcoes)

    # Filtragem
    mask = (
        (df['NF'].astype(str).str.contains(busca, case=False) | 
         df['Item'].astype(str).str.contains(busca, case=False) | 
         df['Fornecedor'].astype(str).str.contains(busca, case=False)) &
        (df['Status'].isin(status_selecionados))
    )
    
    # Selecionamos apenas as colunas que queremos exibir (removendo data_compra)
    colunas_exibicao = ['NF', 'data_emissao', 'Item', 'quantidade', 'Fornecedor', 'meses_garantia', 'data_vencimento', 'Status']
    df_filtrado = df.loc[mask, [c for c in colunas_exibicao if c in df.columns]]

    def style_status(val):
        if '❌' in str(val): return 'background-color: #ffebee; color: #b71c1c; font-weight: bold'
        if '⚠️' in str(val): return 'background-color: #fff3e0; color: #e65100; font-weight: bold'
        if '✅' in str(val): return 'background-color: #e8f5e9; color: #1b5e20; font-weight: bold'
        return ''

    st.dataframe(
        df_filtrado.style.map(style_status, subset=['Status']),
        use_container_width=True,
        hide_index=True,
        column_config={
            "NF": st.column_config.TextColumn("NF"),
            "data_emissao": st.column_config.DateColumn("Emissão", format="DD/MM/YYYY"),
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "quantidade": st.column_config.NumberColumn("Qtd", format="%d"),
            "meses_garantia": st.column_config.NumberColumn("Meses", format="%d"),
            "Status": st.column_config.TextColumn("Status da Garantia")
        }
    )
    st.caption(f"Exibindo {len(df_filtrado)} registros.")
  
# --- ASSINATURA FINALIZADA COM FONTE GABRIOLA ---
st.markdown("---")

st.markdown(
    """
    <div style='text-align: center;'>
        <p style='margin-bottom: 8px; font-family: "Gabriola", serif; font-style: italic; font-size: 18px; color: #0056b3;'>
            Developed by:
        </p>
        <p style='font-family: "Gabriola", serif; font-size: 20px; font-weight: 100; color: #1e7044;'>
            Edison Duarte Filho®
        </p>
    </div>
    """,
    unsafe_allow_html=True
)
