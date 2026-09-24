import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date, datetime
import unicodedata
import re
import json
import time
from PIL import Image
from pydantic import BaseModel, Field
from typing import List
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# 1. CONFIGURAÇÃO DA PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(page_title="InvoiceSis - Gestão de Garantias & Custos", layout="wide")
st.title("🛡️ InvoiceSis | Controle de Garantias e Custos")

# -----------------------------------------------------------------------------
# 2. SCHEMAS DE ESTRUTURAÇÃO PARA A IA (PYDANTIC)
# -----------------------------------------------------------------------------
class ItemNota(BaseModel):
    descricao: str = Field(description="Descrição clara do item ou produto")
    quantidade: float = Field(default=1.0, description="Quantidade comprada")
    valor_unitario: float = Field(default=0.0, description="Valor unitário do item em R$")
    valor_total_item: float = Field(default=0.0, description="Valor total do item em R$")

class NotaFiscal(BaseModel):
    numero_nota: str = Field(default="", description="Número, série ou identificador da Nota Fiscal/Cupom Fiscal")
    data_emissao: str = Field(default="", description="Data de emissão no formato YYYY-MM-DD")
    fornecedor_nome: str = Field(default="", description="Nome do fornecedor, emissor ou razão social")
    valor_total: float = Field(default=0.0, description="Valor total geral da nota fiscal em R$")
    itens: List[ItemNota] = Field(default_factory=list, description="Lista de itens presentes na nota")

# -----------------------------------------------------------------------------
# 3. INICIALIZAÇÃO DO ESTADO GLOBAL (SESSION STATE)
# -----------------------------------------------------------------------------
if 'lista_itens' not in st.session_state:
    st.session_state.lista_itens = []

# Inicialização das chaves do formulário de cadastro/revisão
if 'cad_nf' not in st.session_state:
    st.session_state.cad_nf = ""
if 'cad_data' not in st.session_state:
    st.session_state.cad_data = date.today()
if 'cad_forn' not in st.session_state:
    st.session_state.cad_forn = ""
if 'cad_val_nf' not in st.session_state:
    st.session_state.cad_val_nf = 0.0

# -----------------------------------------------------------------------------
# 4. CONEXÃO COM GOOGLE SHEETS E FUNÇÕES AUXILIARES
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
# 5. FUNÇÃO DE LEITURA DE NF VIA GEMINI (COM FALLBACK PARA GEMINI-2.5-FLASH)
# -----------------------------------------------------------------------------
PROMPT_EXTRACAO = """
Analise esta Nota Fiscal/Cupom Fiscal/DANFE com atenção total aos dados do CABEÇALHO e DOS ITENS:
- Identifique o Número do Documento / Nota Fiscal (ex: Número, NF, Nº, Doc).
- Identifique a Data de Emissão (converta para o formato YYYY-MM-DD).
- Identifique a Razão Social ou Nome Fantasia do Fornecedor/Emissor.
- Identifique o Valor Total Geral do Documento (R$).
- Identifique cada item/produto individual da lista com descrição, quantidade, valor unitário e valor total.
"""

def extrair_com_modelo_gemini(client, modelo, arquivo_bytes, mime_type):
    response = client.models.generate_content(
        model=modelo,
        contents=[
            types.Part.from_bytes(data=arquivo_bytes, mime_type=mime_type),
            PROMPT_EXTRACAO
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=NotaFiscal,
            temperature=0.1
        )
    )
    return json.loads(response.text)

def processar_nota_fiscal(arquivo_bytes, mime_type):
    api_key = st.secrets.get("GEMINI_API_KEY")
    if not api_key:
        api_key = st.secrets.get("connections", {}).get("gsheets", {}).get("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("Chave 'GEMINI_API_KEY' não foi encontrada nos secrets do Streamlit.")

    client = genai.Client(api_key=api_key)

    # 1. TENTATIVA COM O MODELO PRINCIPAL (gemini-3.6-flash)
    try:
        return extrair_com_modelo_gemini(client, 'gemini-3.6-flash', arquivo_bytes, mime_type)
    except Exception as e_principal:
        msg_erro = str(e_principal).upper()
        
        # Se for estouro de cota / limite (429 / RESOURCE_EXHAUSTED / 503 / UNAVAILABLE), aciona o fallback
        if "429" in msg_erro or "RESOURCE_EXHAUSTED" in msg_erro or "503" in msg_erro or "UNAVAILABLE" in msg_erro:
            st.warning("⚠️ Limite ou sobrecarga no modelo principal (Gemini 3.6 Flash). Redirecionando automaticamente para o Gemini 2.5 Flash...")
            
            # 2. TENTATIVA DE FALLBACK DIRETO (gemini-2.5-flash)
            try:
                return extrair_com_modelo_gemini(client, 'gemini-2.5-flash', arquivo_bytes, mime_type)
            except Exception as e_fallback:
                raise RuntimeError(f"Erro no Gemini 3.6: {e_principal} | Erro no Fallback (Gemini 2.5): {e_fallback}")
        else:
            raise e_principal

# -----------------------------------------------------------------------------
# 6. EXPANDER: LEITURA AUTOMÁTICA POR IA (PDF / IMAGEM)
# -----------------------------------------------------------------------------
with st.expander("🤖 Leitura Automática de NF por PDF ou Foto (IA)", expanded=True):
    st.write("Suba o arquivo **PDF** ou a foto (JPG, PNG) da Nota Fiscal para extrair todos os dados automaticamente.")
    
    col_up1, col_up2 = st.columns([1, 1], gap="medium")
    
    with col_up1:
        arquivo_enviado = st.file_uploader("Selecione o arquivo (PDF, JPG, PNG)", type=["pdf", "jpg", "jpeg", "png"], key="ia_uploader")
        
        if arquivo_enviado:
            nome_arquivo = arquivo_enviado.name.lower()
            bytes_data = arquivo_enviado.getvalue()
            
            if nome_arquivo.endswith(".pdf"):
                mime_type = "application/pdf"
                st.info(f"📄 Arquivo PDF carregado: **{arquivo_enviado.name}**")
            else:
                imagem = Image.open(arquivo_enviado)
                st.image(imagem, caption="Nota Carregada", use_container_width=True)
                fmt = imagem.format if imagem.format else "PNG"
                mime_type = f"image/{fmt.lower()}"
            
            if st.button("🚀 Extrair Dados da Nota", type="primary"):
                with st.spinner("Analisando o documento com IA..."):
                    try:
                        dados = processar_nota_fiscal(bytes_data, mime_type)

                        if dados:
                            # Tratamento seguro do Número da NF
                            raw_nf = str(dados.get("numero_nota", "")).strip()
                            nf_num = raw_nf if raw_nf and raw_nf.lower() != "null" else "S/N"

                            # Tratamento seguro do Fornecedor
                            raw_forn = str(dados.get("fornecedor_nome", "")).strip()
                            forn = raw_forn if raw_forn and raw_forn.lower() != "null" else "Fornecedor Não Identificado"

                            # Tratamento seguro da Data de Emissão
                            dt_emissao_str = str(dados.get("data_emissao", "")).strip()
                            try:
                                dt_emissao_obj = datetime.strptime(dt_emissao_str, '%Y-%m-%d').date()
                            except:
                                dt_emissao_obj = date.today()

                            # Tratamento seguro do Valor Total
                            try:
                                v_total_nf = float(dados.get("valor_total", 0.0))
                            except:
                                v_total_nf = 0.0

                            # ATUALIZAÇÃO DIRETA NO SESSION STATE
                            st.session_state.cad_nf = nf_num
                            st.session_state.cad_data = dt_emissao_obj
                            st.session_state.cad_forn = forn
                            st.session_state.cad_val_nf = v_total_nf

                            # Limpa a lista para receber os itens da nova nota
                            st.session_state.lista_itens = []

                            itens_lidos = dados.get("itens", [])
                            garantia_padrao = 12

                            for it in itens_lidos:
                                desc = str(it.get("descricao", "Item Sem Nome")).strip()
                                try:
                                    qtd = int(float(it.get("quantidade", 1)))
                                    if qtd <= 0: qtd = 1
                                except:
                                    qtd = 1
                                
                                try:
                                    v_unit = float(it.get("valor_unitario", 0.0))
                                except:
                                    v_unit = 0.0

                                try:
                                    v_tot_item = float(it.get("valor_total_item", 0.0))
                                    if v_tot_item == 0.0 and v_unit > 0:
                                        v_tot_item = round(qtd * v_unit, 2)
                                except:
                                    v_tot_item = round(qtd * v_unit, 2)

                                dt_venc = pd.to_datetime(dt_emissao_obj) + pd.DateOffset(months=garantia_padrao)

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

                            st.success(f"✅ Sucesso! Extraído: NF Nº **{nf_num}** | Fornecedor: **{forn}** | Valor Total: **R$ {v_total_nf:,.2f}** | Itens: **{len(itens_lidos)}**")
                            st.rerun()

                    except Exception as e:
                        st.error(f"Não foi possível processar a nota fiscal: {e}")

# -----------------------------------------------------------------------------
# 7. FORMULÁRIO DE CADASTRO MANUAL OU REVISÃO DA IA
# -----------------------------------------------------------------------------
def limpar_formulario():
    st.session_state.lista_itens = []
    for key in ['cad_nf', 'cad_data', 'cad_forn', 'cad_val_nf']:
        if key in st.session_state:
            del st.session_state[key]

with st.expander("📝 Cadastrar / Revisar Itens para Salvar", expanded=True if (st.session_state.lista_itens or st.session_state.get('cad_nf')) else False):
    st.markdown("#### Cabeçalho da Nota Fiscal")
    c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1])
    
    nf_comum = c1.text_input("Número da NF", key="cad_nf")
    data_emissao_comum = c2.date_input("Data da Emissão", format="DD/MM/YYYY", key="cad_data")
    fornecedor_comum = c3.text_input("Fornecedor", key="cad_forn")
    valor_total_nf_comum = c4.number_input("Valor Total da NF (R$)", min_value=0.0, step=10.0, format="%.2f", key="cad_val_nf")

    st.divider()
    st.markdown("#### Adicionar / Revisar Itens da Nota")
    
    ca, cb, cc, cd = st.columns([2, 1, 1, 1])
    item_nome = ca.text_input("Descrição do Item / Material", key="cad_item")
    item_qtd = cb.number_input("Quantidade", min_value=1, value=1, key="cad_qtd")
    item_valor_uni = cc.number_input("Valor Unitário (R$)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="cad_val_uni")
    item_garantia = cd.number_input("Garantia (Meses)", min_value=1, value=12, key="cad_gar")
    
    if st.button("➕ Adicionar Item à Lista Manualmente"):
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
            st.rerun()
        else:
            st.error("Preencha o número da NF e a Descrição do Item.")

    if st.session_state.lista_itens:
        st.write("---")
        st.subheader("📋 Itens Extraídos Prontos para Gravação")
        
        # Sincroniza o cabeçalho caso o usuário altere os campos do topo antes de salvar
        for item in st.session_state.lista_itens:
            item["NF"] = str(st.session_state.cad_nf).strip()
            item["data_emissao"] = st.session_state.cad_data.strftime('%Y-%m-%d')
            item["Fornecedor"] = st.session_state.cad_forn
            item["valor_total_nf"] = float(st.session_state.cad_val_nf)

        df_temp = pd.DataFrame(st.session_state.lista_itens)
        st.dataframe(df_temp[['NF', 'data_emissao', 'Fornecedor', 'valor_total_nf', 'Item', 'quantidade', 'valor_unitario', 'valor_total_item', 'meses_garantia']], use_container_width=True)
        
        col_btn1, col_btn2 = st.columns(2)
        col_btn1.button("🗑️ Limpar Formulário", on_click=limpar_formulario)

        if col_btn2.button("💾 SALVAR TUDO NO GOOGLE SHEETS", type="primary"):
            try:
                df_novos = pd.DataFrame(st.session_state.lista_itens)
                df_final = pd.concat([df_existente, df_novos], ignore_index=True)
                url_planilha = st.secrets["connections"]["gsheets"]["spreadsheet"]
                conn.update(spreadsheet=url_planilha, worksheet="Garantias", data=df_final)
                st.success("✅ Salvo com sucesso no Google Sheets!")
                time.sleep(1)
                limpar_formulario()
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

# -----------------------------------------------------------------------------
# 8. HISTÓRICO, FILTROS E SOMAS FINANCEIRAS
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

    busca_rapida = st.text_input("🔍 Busca Rápida Avançada:", placeholder="Digite qualquer termo para filtrar a tabela...").strip()
    busca_rapida_norm = normalizar_texto(busca_rapida)

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
    buscar_materiais = c_mat.multiselect("📦 Filtrar por Material(is)", options=lista_materiais, default=None)
    buscar_fornecedores = c_forn.multiselect("🏭 Filtrar por Fornecedor(es)", options=lista_fornecedores, default=None)
    buscar_nfs = c_nf.multiselect("🧾 Filtrar por Nota(s)", options=lista_nfs, default=None)
    status_selecionados = c_stat.multiselect("🛡️ Status da Garantia", options=status_opcoes, default=status_opcoes)

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
            "data_vencimento": st.column_config.DateColumn("Vencimento", format="DD/MM/YYYY")
        }
    )

# -----------------------------------------------------------------------------
# 9. ASSINATURA
# -----------------------------------------------------------------------------
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; margin-top: 40px; padding-bottom: 20px;'>
        <div style='font-family: "Gabriola", serif; font-style: italic; font-size: 18px; color: #0056b3;'>
            Developed by:
        </div>
        <div style='font-family: "Gabriola", serif; font-size: 22px; font-weight: bold; color: #1e7044; margin-top: 4px;'>
            Edison Duarte Filho®
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
