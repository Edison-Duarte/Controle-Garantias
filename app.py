import streamlit as st
from streamlit_gsheets import GSheetsConnection

# Configuração da página para o projeto de Garantias
st.set_page_config(page_title="Controle de Garantias", layout="wide")

# Título Principal
st.title("🛡️ Sistema de Controle de Garantias")

# Estabelecendo a conexão com o Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Função para carregar os dados da planilha de garantias
def load_data():
    try:
        # Busca a URL da planilha diretamente dos secrets configurados
        url = st.secrets["connections"]["gsheets"]["spreadsheet"]
        # Lê os dados da aba principal (ajuste 'Sheet1' se o nome da aba for outro)
        return conn.read(spreadsheet=url, worksheet="Sheet1")
    except Exception as e:
        st.error(f"Erro ao acessar a planilha: {e}")
        return None

# Execução do carregamento
df = load_data()

if df is not None:
    # Área de filtros e busca
    st.subheader("Consulta de Registros")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        busca = st.text_input("Pesquisar por Cliente, Produto ou Número de Série:")
    
    # Lógica de filtragem
    if busca:
        mask = df.astype(str).apply(lambda x: x.str.contains(busca, case=False)).any(axis=1)
        df_exibicao = df[mask]
    else:
        df_exibicao = df

    # Exibição dos dados
    st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

    # Resumo rápido (opcional)
    if not df_exibicao.empty:
        st.info(f"Exibindo {len(df_exibicao)} registro(s) encontrado(s).")
else:
    st.warning("Aguardando conexão com a base de dados...")

# Rodapé
st.markdown("---")
st.caption("Controle de Garantias v1.0 | Conectado via Streamlit Secrets")
