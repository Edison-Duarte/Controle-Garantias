import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date, datetime
import unicodedata
import re
import json
import io
from PIL import Image
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(page_title="InvoiceSis - Gestão de Garantias & Custos", layout="wide")
st.title("🛡️ InvoiceSis | Controle de Garantias e Custos")

# -----------------------------------------------------------------------------
# 2. CONEXÃO COM GOOGLE SHEETS E FUNÇÕES AUXILIARES
# -----------------------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def normalizar_texto(texto):
    if pd.isnull(texto) or not isinstance(texto, str):
        return ""
    texto = texto.lower()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^\w\s]', '', texto)
    return " ".join(texto.split())

def carregar_dados():
    try:
        url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
        df = conn.read(spreadsheet=url_planilha, worksheet="Garantias", ttl=0)
        if df is not None and not df.empty:
            df = df.dropna(how='all')
            if 'NF' in df.columns:
                df['NF'] = df['NF'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            for col in ['meses_garantia', 'quantidade']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            for col in ['valor_unitario', 'valor_total_item', 'valor_total_nf']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)
            
            colunas_data = ['data_emissao', 'data_vencimento']
            for col in colunas_data:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df
    except Exception as e:
        return pd.DataFrame(columns=['NF', 'data_emissao', 'valor_total_nf', 'Item', 'quantidade', 'valor_unitario', 'valor_total_item', 'Fornecedor', 'meses_garantia', 'data_vencimento'])

df_existente = carregar_dados()

# -----------------------------------------------------------------------------
# 3. FUNÇÃO DE LEITURA DE NF VIA GEMINI API (SUPORTE A IMAGENS E PDF)
# -----------------------------------------------------------------------------
def processar_nota_fiscal(arquivo_bytes, mime_type):
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        api_key = st.secrets.get("connections", {}).get("gsheets", {}).get("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("Chave 'GEMINI_API_KEY' não foi encontrada nos secrets do Streamlit.")

    client = genai.Client(api_key=api_key)

    prompt = """
    Analise esta imagem ou documento PDF de Nota Fiscal (NFe, NFCe, DANFE ou Cupom Fiscal) e extraia exatamente as informações abaixo no formato JSON.

    Estrutura JSON obrigatória:
    {
        "numero_nota": "string",
        "data_emissao": "YYYY-MM-DD",
        "fornecedor_nome": "string",
        "valor_total": float,
        "itens": [
            {
                "descricao": "string",
                "quantidade": float,
                "valor_unitario": float,
                "valor_total_item": float
            }
        ]
    }

    Regras:
    1. Retorne APENAS o objeto JSON válido.
    2. Se não encontrar algum campo textual, use "" (string vazia).
    3. Se não encontrar algum valor numérico, use 0.0.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            prompt
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )

    return json.loads(response.text)

# -----------------------------------------------------------------------------
# 4. ESTADO DA SESSÃO
# -----------------------------------------------------------------------------
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# -----------------------------------------------------------------------------
# 5. EXPANDER: LEITURA AUTOMÁTICA POR IA (PDF / IMAGEM)
# -----------------------------------------------------------------------------
with st.expander("🤖 Leitura Automática de NF por PDF ou Foto (IA)", expanded=False):
    st.write("Suba o arquivo **PDF** ou a foto (JPG, PNG) da Nota Fiscal para extrair os dados automaticamente.")
    
    col_up1, col_up2 = st.columns([1, 1], gap="medium")
    
    with col_up1:
        # Adicionado suporte a "pdf" no type
        arquivo_enviado = st.file_uploader("Selecione o arquivo (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"], key="ia_uploader")
        
        if arquivo_enviado:
            nome_arquivo = arquivo_enviado.name.lower()
            bytes_data = arquivo_enviado.getvalue()
            
            # Identificação do MIME TYPE correto
            if nome_arquivo.endswith(".pdf"):
                mime_type = "application/pdf"
                st.info(f"📄 Arquivo PDF carregado: **{arquivo_enviado.name}**")
            else:
                imagem = Image.open(arquivo_enviado)
                st.image(imagem, caption="Nota Carregada", use_container_width=True)
                fmt = imagem.format if imagem.format else "PNG"
                mime_type = f"image/{fmt.lower()}"
            
            if st.button("🚀 Extrair Dados da Nota", type="primary"):
                with st.spinner("O Gemini está analisando o documento..."):
                    try:
                        dados = processar_nota_fiscal(bytes_data, mime_type)

                        # Adiciona automaticamente os itens lidos para a lista temporária do sistema
                        nf_num = str(dados.get("numero_nota", "")).strip()
                        dt_emissao_str = dados.get("data_emissao", date.today().strftime('%Y-%m-%d'))
                        
                        try:
                            dt_emissao_obj = datetime.strptime(dt_emissao_str, '%Y-%m-%d')
                        except:
                            dt_emissao_obj = datetime.now()

                        forn = dados.get("fornecedor_nome", "")
                        v_total_nf = float(dados.get("valor_total", 0.0))

                        itens_lidos = dados.get("itens", [])
                        garantia_padrao = 12 # Meses de garantia padrão

                        for it in itens_lidos:
                            desc = it.get("descricao", "Item Sem Nome")
                            qtd = int(it.get("quantidade", 1)) if it.get("quantidade", 1) > 0 else 1
                            v_unit = float(it.get("valor_unitario", 0.0))
                            v_tot_item = float(it.get("valor_total_item", qtd * v_unit))
                            
                            dt_venc = dt_emissao_obj + pd.DateOffset(months=garantia_padrao)

                            st.session_state.lista_itens.append({
                                "NF": nf_num,
                                "data_emissao": dt_emissao_obj.strftime('%Y-%m-%d'),
                                "valor_total_nf": v_total_nf,
                                "Item": desc,
                                "quantidade": qtd,
                                "valor_unitario": v_unit,
                                "valor_total_item": v_tot_item,
                                "Fornecedor": forn,
                                "meses_garantia": garantia_padrao,
                                "data_vencimento": dt_venc.strftime('%Y-%m-%d')
                            })

                        st.success(f"✅ {len(itens_lidos)} item(ns) extraído(s) com sucesso! Confira abaixo no formulário antes de salvar.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro no processamento da nota: {e}")

# -----------------------------------------------------------------------------
# 6. FORMULÁRIO DE CADASTRO MANUAL OU REVISÃO DA IA
# -----------------------------------------------------------------------------
with st.expander("📝 Cadastrar / Revisar Itens para Salvar", expanded=True if st.session_state.lista_itens else False):
    st.markdown("#### Adicionar Item Manualmente")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    nf_comum = c1.text_input("Número da NF", key="cad_nf")
    data_emissao_comum = c2.date_input("Data da Emissão", value=date.today(), format="DD/MM/YYYY", key="cad_data")
    fornecedor_comum = c3.text_input("Fornecedor", key="cad_forn")
    valor_total_nf_comum = c4.number_input("Valor Total da NF (R$)", min_value=0.0, value=0.0, step=10.0, format="%.2f", key="cad_val_nf")

    st.divider()
    
    ca, cb, cc, cd = st.columns([2, 1, 1, 1])
    item_nome = ca.text_input("Descrição do Item / Material", key="cad_item")
    item_qtd = cb.number_input("Quantidade", min_value=1, value=1, key="cad_qtd")
    item_valor_uni = cc.number_input("Valor Unitário (R$)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="cad_val_uni")
    item_garantia = cd.number_input("Garantia (Meses)", min_value=1, value=12, key="cad_gar")
    
    if st.button("➕ Adicionar à Lista Manualmente"):
        if item_nome and nf_comum:
            dt_emissao = pd.to_datetime(data_emissao_comum)
            dt_venc = dt_emissao + pd.DateOffset(months=int(item_garantia))
            v_total_item = float(item_qtd * item_valor_uni)
            
            st.session_state.lista_itens.append({
                "NF": str(nf_comum).strip(),
                "data_emissao": data_emissao_comum.strftime('%Y-%m-%d'),
                "valor_total_nf": float(valor_total_nf_comum),
                "Item": item_nome,
                "quantidade": int(item_qtd),
                "valor_unitario": float(item_valor_uni),
                "valor_total_item": v_total_item,
                "Fornecedor": fornecedor_comum,
                "meses_garantia": int(item_garantia),
                "data_vencimento": dt_venc.strftime('%Y-%m-%d')
            })
            st.toast(f"Item '{item_nome}' adicionado!")
        else:
            st.error("Preencha o número da NF e a Descrição do Item.")

    # Exibe a lista acumulada (seja da IA ou manual)
    if st.session_state.lista_itens:
        st.write("---")
        st.subheader("📋 Itens Prontos para Gravação")
        df_temp = pd.DataFrame(st.session_state.lista_itens)
        st.dataframe(df_temp[['NF', 'Fornecedor', 'Item', 'quantidade', 'valor_unitario', 'valor_total_item', 'meses_garantia']], use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        if col_btn1.button("🗑️ Limpar Lista"):
            st.session_state.lista_itens = []
            st.rerun()

        if col_btn2.button("💾 SALVAR TUDO NO GOOGLE SHEETS", type="primary"):
            try:
                df_novos = pd.DataFrame(st.session_state.lista_itens)
                df_final = pd.concat([df_existente, df_novos], ignore_index=True)
                url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_final)
                st.success("✅ Salvo com sucesso no Google Sheets!")
                st.session_state.lista_itens = []
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# -----------------------------------------------------------------------------
# 7. HISTÓRICO, FILTROS E SOMAS FINANCEIRAS
# -----------------------------------------------------------------------------
st.divider()
st.subheader("📊 Consulta e Relatório de Gastos")
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

    # 1. BARRA DE PESQUISA GLOBAL
    busca_rapida = st.text_input("🔍 Busca Rápida Avançada (Pode digitar sem acentos, ex: 'lampada', 'luminaria', 'fornecedor'):", placeholder="Digite qualquer termo para filtrar a tabela inteira...").strip()
    busca_rapida_norm = normalizar_texto(busca_rapida)

    # 2. FILTRO POR PERÍODO DE EMISSÃO DA NF
    col_dt1, col_dt2 = st.columns(2)
    datas_validas = [d for d in df['data_emissao'].dropna() if isinstance(d, date)]
    dt_min_def = min(datas_validas) if datas_validas else date(2020, 1, 1)
    dt_max_def = max(datas_validas) if datas_validas else date.today()

    dt_inicio = col_dt1.date_input("📅 Data Inicial (Emissão NF)", value=dt_min_def, format="DD/MM/YYYY", key="filtro_dt_inicio")
    dt_fim = col_dt2.date_input("📅 Data Final (Emissão NF)", value=dt_max_def, format="DD/MM/YYYY", key="filtro_dt_fim")

    lista_materiais = sorted(df['Item'].dropna().unique().tolist())
    lista_fornecedores = sorted(df['Fornecedor'].dropna().unique().tolist())
    lista_nfs = sorted(df['NF'].dropna().unique().tolist())
    status_opcoes = ["✅ ATIVA", "⚠️ VENCE EM BREVE", "❌ EXPIRADA", "⚪ SEM DATA"]

    c_mat, c_forn, c_nf, c_stat = st.columns([1.5, 1.5, 1, 1])
    buscar_materiais = c_mat.multiselect("📦 Filtrar por Material(is) da Lista", options=lista_materiais, default=None, placeholder="Todos os materiais")
    buscar_fornecedores = c_forn.multiselect("🏭 Filtrar por Fornecedor(es) da Lista", options=lista_fornecedores, default=None, placeholder="Todos os fornecedores")
    buscar_nfs = c_nf.multiselect("🧾 Filtrar por Nota(s)", options=lista_nfs, default=None, placeholder="Todas as NFs")
    status_selecionados = c_stat.multiselect("🛡️ Status da Garantia", options=status_opcoes, default=status_opcoes)

    # Filtragem combinada
    mask = df['Status'].isin(status_selecionados)
    df_datas_emissao = pd.to_datetime(df['data_emissao'], errors='coerce').dt.date

    if dt_inicio and dt_fim:
        mask = mask & (df_datas_emissao >= dt_inicio) & (df_datas_emissao <= dt_fim)

    if busca_rapida_norm:
        mask = mask & (
            df['Item'].apply(normalizar_texto).str.contains(busca_rapida_norm, case=False, na=False) |
            df['Fornecedor'].apply(normalizar_texto).str.contains(busca_rapida_norm, case=False, na=False) |
            df['NF'].apply(normalizar_texto).str.contains(busca_rapida_norm, case=False, na=False)
        )

    if buscar_materiais:
        materiais_norm = [normalizar_texto(m) for m in buscar_materiais]
        mask = mask & (df['Item'].apply(normalizar_texto).isin(materiais_norm))
        
    if buscar_fornecedores:
        fornecedores_norm = [normalizar_texto(f) for f in buscar_fornecedores]
        mask = mask & (df['Fornecedor'].apply(normalizar_texto).isin(fornecedores_norm))
        
    if buscar_nfs:
        nfs_norm = [normalizar_texto(n) for n in buscar_nfs]
        mask = mask & (df['NF'].apply(normalizar_texto).isin(nfs_norm))
    
    colunas_exibicao = ['NF', 'data_emissao', 'valor_total_nf', 'Item', 'quantidade', 'valor_unitario', 'valor_total_item', 'Fornecedor', 'meses_garantia', 'data_vencimento', 'Status']
    df_filtrado = df.loc[mask, [c for c in colunas_exibicao if c in df.columns]].copy()
    df_filtrado['ID_Original'] = df_filtrado.index

    # Métricas Dinâmicas
    total_gasto = df_filtrado['valor_total_item'].sum() if 'valor_total_item' in df_filtrado.columns else 0.0
    total_qtd = df_filtrado['quantidade'].sum() if 'quantidade' in df_filtrado.columns else 0
    
    m1, m2 = st.columns(2)
    m1.metric(label="💰 Total Gasto Selecionado", value=f"R$ {total_gasto:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    m2.metric(label="📦 Quantidade Total Acumulada", value=f"{total_qtd} un")

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
            "valor_total_nf": st.column_config.NumberColumn("Total NF", format="R$ %.2f"),
            "Item": st.column_config.TextColumn("Material / Item"),
            "quantidade": st.column_config.NumberColumn("Qtd", format="%d"),
            "valor_unitario": st.column_config.NumberColumn("Val. Unitário", format="R$ %.2f"),
            "valor_total_item": st.column_config.NumberColumn("Total Item", format="R$ %.2f"),
            "meses_garantia": st.column_config.NumberColumn("Meses", format="%d"),
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY"),
            "ID_Original": None
        }
    )
    
    # -------------------------------------------------------------------------
    # 8. PAINEL DE MODIFICAÇÃO DE REGISTROS
    # -------------------------------------------------------------------------
    st.write("---")
    with st.expander("✏️ Painel de Modificação de Registros (Editar, Desconto ou Apagar)"):
        
        busca_interna = st.text_input("🔍 Procurar nota para modificar por número, fornecedor ou item:", key="busca_painel").strip()
        busca_interna_norm = normalizar_texto(busca_interna)
        
        if busca_interna_norm:
            mask_interna = (
                df['NF'].apply(normalizar_texto).str.contains(busca_interna_norm, case=False, na=False) |
                df['Fornecedor'].apply(normalizar_texto).str.contains(busca_interna_norm, case=False, na=False) |
                df['Item'].apply(normalizar_texto).str.contains(busca_interna_norm, case=False, na=False)
            )
            df_opcoes = df[mask_interna]
        else:
            df_opcoes = df

        lista_opcoes_edicao = {}
        for idx, row in df_opcoes.iterrows():
            v_item_str = f"R$ {float(row['valor_total_item']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            texto_opcao = f"NF: {row['NF']} | Forn: {row['Fornecedor']} | Item: {row['Item']} ({v_item_str}) (Ref: {idx})"
            lista_opcoes_edicao[texto_opcao] = idx
            
        if lista_opcoes_edicao:
            item_para_editar = st.selectbox("Selecione o registro encontrado desejado:", options=list(lista_opcoes_edicao.keys()))
            
            if item_para_editar:
                idx_real_planilha = lista_opcoes_edicao[item_para_editar]
                registro_selecionado = df.loc[idx_real_planilha]
                
                with st.form(key=f"form_edicao_{idx_real_planilha}"):
                    st.write("✏️ *Modifique apenas os campos necessários:*")
                    
                    ed_c1, ed_c2, ed_c3, ed_c4 = st.columns([1, 1, 1, 1])
                    ed_nf = ed_c1.text_input("Número da NF", value=str(registro_selecionado['NF']))
                    ed_data = ed_c2.date_input("Data da Emissão", value=pd.to_datetime(registro_selecionado['data_emissao']).date(), format="DD/MM/YYYY")
                    ed_forn = ed_c3.text_input("Fornecedor", value=str(registro_selecionado['Fornecedor']))
                    ed_total_nf = ed_c4.number_input("Valor Total da NF (R$)", min_value=0.0, value=float(registro_selecionado['valor_total_nf']), step=10.0, format="%.2f")
                    
                    ed_ca, ed_cb, ed_cc, ed_cd = st.columns([2, 1, 1, 1])
                    ed_item = ed_ca.text_input("Descrição do Item", value=str(registro_selecionado['Item']))
                    ed_qtd = ed_cb.number_input("Quantidade", min_value=1, value=int(registro_selecionado['quantidade']))
                    ed_uni = ed_cc.number_input("Valor Unitário (R$)", min_value=0.0, value=float(registro_selecionado['valor_unitario']), step=1.0, format="%.2f")
                    ed_gar = ed_cd.number_input("Garantia (Meses)", min_value=1, value=int(registro_selecionado['meses_garantia']))
                    
                    st.markdown("**🏷️ Aplicar Desconto / Abatimento de Valor**")
                    desconto_val = st.number_input("Valor do Desconto a Abater no Item/NF (R$)", min_value=0.0, value=0.0, step=5.0, format="%.2f", help="Digite o valor a abater. O sistema atualizará o total do item e o total da NF.")

                    st.write("")
                    btn_col1, btn_col2, btn_col3 = st.columns([1.2, 1.2, 1])
                    
                    salvar_alteracao = btn_col1.form_submit_button("💾 Salvar Alterações", type="primary", use_container_width=True)
                    aplicar_desconto = btn_col2.form_submit_button("🏷️ Aplicar Desconto", use_container_width=True)
                    apagar_registro = btn_col3.form_submit_button("❌ Apagar Registro", type="secondary", use_container_width=True)

                    if salvar_alteracao:
                        try:
                            dt_emissao_ed = pd.to_datetime(ed_data)
                            dt_venc_ed = dt_emissao_ed + pd.DateOffset(months=int(ed_gar))
                            v_total_item_ed = float(ed_qtd * ed_uni)
                            
                            df.at[idx_real_planilha, 'NF'] = str(ed_nf).strip()
                            df.at[idx_real_planilha, 'data_emissao'] = ed_data.strftime('%Y-%m-%d')
                            df.at[idx_real_planilha, 'valor_total_nf'] = float(ed_total_nf)
                            df.at[idx_real_planilha, 'Item'] = ed_item
                            df.at[idx_real_planilha, 'quantidade'] = int(ed_qtd)
                            df.at[idx_real_planilha, 'valor_unitario'] = float(ed_uni)
                            df.at[idx_real_planilha, 'valor_total_item'] = v_total_item_ed
                            df.at[idx_real_planilha, 'Fornecedor'] = ed_forn
                            df.at[idx_real_planilha, 'meses_garantia'] = int(ed_gar)
                            df.at[idx_real_planilha, 'data_vencimento'] = dt_venc_ed.strftime('%Y-%m-%d')
                            
                            if 'Status' in df.columns: df = df.drop(columns=['Status'])
                            if 'ID_Original' in df.columns: df = df.drop(columns=['ID_Original'])
                            
                            url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                            conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df)
                            st.success("✅ Alteração gravada com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao atualizar: {e}")

                    if aplicar_desconto:
                        if desconto_val <= 0:
                            st.warning("Informe um valor de desconto maior que zero.")
                        else:
                            try:
                                v_item_atual = float(registro_selecionado['valor_total_item'])
                                v_nf_atual = float(registro_selecionado['valor_total_nf'])
                                qtd_atual = max(1, int(ed_qtd))

                                novo_v_item = max(0.0, v_item_atual - desconto_val)
                                novo_v_nf = max(0.0, v_nf_atual - desconto_val)
                                novo_v_unitario = round(novo_v_item / qtd_atual, 2)

                                df.at[idx_real_planilha, 'valor_total_item'] = novo_v_item
                                df.at[idx_real_planilha, 'valor_total_nf'] = novo_v_nf
                                df.at[idx_real_planilha, 'valor_unitario'] = novo_v_unitario

                                if 'Status' in df.columns: df = df.drop(columns=['Status'])
                                if 'ID_Original' in df.columns: df = df.drop(columns=['ID_Original'])

                                url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                                conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df)
                                st.success(f"🏷️ Desconto de R$ {desconto_val:.2f} aplicado com sucesso!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro ao aplicar desconto: {e}")
                    
                    if apagar_registro:
                        try:
                            df = df.drop(index=idx_real_planilha)
                            
                            if 'Status' in df.columns: df = df.drop(columns=['Status'])
                            if 'ID_Original' in df.columns: df = df.drop(columns=['ID_Original'])
                            
                            url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                            conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df)
                            st.success("🗑️ Registro apagado com sucesso!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao excluir o registro: {e}")
        else:
            st.warning("Nenhum registro correspondente encontrado na busca interna.")
                        
    st.caption(f"Exibindo {len(df_filtrado)} registros encontrados.")

# -----------------------------------------------------------------------------
# 9. ASSINATURA
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; margin-top: 40px; padding-bottom: 20px;'>
        <div style='font-family: "Gabriola", serif; font-style: italic; font-size: 18px; color: #0056b3; line-height: 1.2;'>
            Developed by:
        </div>
        <div style='font-family: "Gabriola", serif; font-size: 22px; font-weight: bold; color: #1e7044; line-height: 1.2; margin-top: 4px;'>
            Edison Duarte Filho®
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
