import streamlit as st
import pandas as pd  
import numpy as np  
import datetime  
import matplotlib.pyplot as plt  
import seaborn as sns  
import base64  
from io import BytesIO  
import re
  
from langchain.tools import Tool  
from langchain.agents import create_tool_calling_agent, AgentExecutor  
from langchain_openai import ChatOpenAI  
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder 
from langchain.memory import ConversationBufferWindowMemory 
from langchain_community.callbacks import get_openai_callback  
  
from dotenv import load_dotenv  
from pathlib import Path  
import os

st.set_page_config(
    page_title="ChatPELT", 
    page_icon="🏢",
    layout="wide"
)

# --- ESTILIZAÇÃO CUSTOMIZADA ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');

    /* Aplicar Montserrat para todo o app */
    html, body, [class*="st-"], .stApp, h1, h2, h3, p, div, span, button {
        font-family: 'Montserrat', sans-serif !important;
    }

    /* Cor dos 'chips' (selecionados) no multiselect */
    span[data-baseweb="tag"] {
        background-color: #9BA0BF !important;
        border-radius: 4px;
    }
    
    /* Cor de fundo dos campos de seleção e inputs */
    div[data-baseweb="select"] > div, 
    div[data-baseweb="base-input"],
    .stTextInput input {
        background-color: #BAD6D9 !important;
        color: #1b1b1b !important;
    }

    /* Garantir que o texto dos selecionados seja visível */
    span[data-baseweb="tag"] span {
        color: white !important;
    }

    /* Estilização das métricas (Visão Geral) */
    [data-testid="stMetric"] {
        text-align: center;
        padding: 15px;
        background-color: #BAD6D933; /* Fundo suave para os cards */
        border-radius: 10px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }

    [data-testid="stMetricLabel"] p {
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: #192E40 !important;
        display: flex;
        justify-content: center;
        text-align: center !important;
        width: 100%;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        color: #192E40 !important;
        width: 100%;
        text-align: center !important;
        display: flex;
        justify-content: center;
    }

    /* Estilo Criativo para o Botão Limpar Filtros */
    .stButton > button {
        transition: all 0.3s ease-in-out !important;
    }

    div[data-testid="column"] button[kind="secondary"] {
        background: linear-gradient(135deg, #9BA0BF 0%, #192E40 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 30px !important; /* Formato Pílula */
        padding: 0.5rem 2rem !important;
        font-weight: 600 !important;
        letter-spacing: 1px !important;
        text-transform: uppercase !important;
        font-size: 0.8rem !important;
        box-shadow: 0 4px 15px rgba(25, 46, 64, 0.2) !important;
    }

    div[data-testid="column"] button[kind="secondary"]:hover {
        transform: scale(1.05) !important;
        box-shadow: 0 6px 20px rgba(155, 160, 191, 0.4) !important;
        opacity: 0.9 !important;
    }

    div[data-testid="column"] button[kind="secondary"]:active {
        transform: scale(0.95) !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
  
ultimo_grafico_base64 = None

# --- CONFIGURAÇÃO INICIAL ---

dotenv_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path)
api_key = os.getenv("OPENAI_API_KEY")
#api_key = st.secrets["OPENAI_API_KEY"]

  
# Uso do st.cache_data para evitar recarregar o arquivo em cada nova aba
@st.cache_data
def carregar_dados():
    try:  
        df_parquet = pd.read_parquet('dados_consolidados.parquet')
        df_json = pd.read_json("dadospelt/tbl_alocacaoempreendimento.json")
        df_json_norm = pd.json_normalize(df_json['tbl_alocacaoempreendimento'])
        return df_parquet, df_json_norm
    except Exception as e:  
        print(f"Erro ao carregar o dataframe: {e}")  
        st.stop() 

df, df_alocemp = carregar_dados()

try:
    with open("prompt.md", "r", encoding="utf-8") as f:  
        system_prompt = f.read()
except Exception as e:  
    print(f"Erro ao carregar o prompt: {e}")  
    st.stop() 

# --- FERRAMENTA DE CONSULTA ---  
  
def query_dataframe(query: str) -> str:
    try:
        safe_env = {
            'df': df,
            'df_alocemp': df_alocemp,
            'pd': pd,
            'np': np,
            'result': None
        }
        if '\n' in query:
            lines = query.strip().split('\n')
            last_line = lines[-1].strip()
            if '=' not in last_line and not last_line.startswith('print'):
                lines[-1] = f"result = {last_line}"
            elif last_line.startswith('print'):
                lines[-1] = f"result = {last_line[6:-1]}"
            exec('\n'.join(lines), safe_env)
            result = safe_env.get('result')
            if result is None:
                for line in reversed(lines):
                    if '=' in line:
                        var_name = line.split('=')[0].strip()
                        if var_name in safe_env:
                            result = safe_env[var_name]
                            break
        else:
            result = eval(query, {}, safe_env)
        if result is None:
            return "Operação executada (sem retorno)"
        if isinstance(result, (pd.DataFrame, pd.Series)):
            if len(result) > 24:
                return (
                    f"Resultado truncado (24 de {len(result)} linhas):\n"
                    f"{result.head(24).to_string()}"
                )
            return f"Resultado:\n{result.to_string()}"
        if isinstance(result, (list, dict, set)):
            return f"Resultado ({type(result).__name__}):\n{str(result)[:500]}"
        return f"Resultado: {str(result)[:500]}"
    except Exception as e:
        return f"ERRO: {str(e)}\nDica: Use 'df' ou 'df_alocemp' para referenciar os DataFrames"
  
def plot_chart(query: str) -> str:  
    try:  
        plt.style.use('default')  
        fig, ax = plt.subplots(figsize=(10, 6))  
          
        safe_env = {  
            'df': df,  
            'df_alocemp': df_alocemp,  
            'pd': pd,  
            'np': np,  
            'plt': plt,  
            'sns': sns,  
            'fig': fig,  
            'ax': ax  
        }  
          
        exec(query, safe_env)  
          
        buffer = BytesIO()  
        plt.tight_layout()  
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')  
        buffer.seek(0)  
          
        img_base64 = base64.b64encode(buffer.getvalue()).decode()  
        plt.close()  
          
        global ultimo_grafico_base64  
        ultimo_grafico_base64 = img_base64  
          
        return "GRAFICO_CRIADO_COM_SUCESSO"  
          
    except Exception as e:  
        plt.close()  
        return f"ERRO ao criar gráfico: {str(e)}"  
  
# --- CONFIGURAÇÃO DO AGENTE ---  
  
tools = [  
    Tool(  
        name="dataframe_query",  
        func=query_dataframe,  
        description="""Ferramenta para consultar os DataFrames já carregados.  
       Use essa ferramenta para fazer consultas usando pandas nos dataframes: df, df_alocemp.
       Use pd.merge() com 'id_empreendimento' para cruzar dados entre eles."""  
    ),  
    Tool(  
        name="plot_chart",  
        func=plot_chart,  
        description="""Ferramenta para criar gráficos usando matplotlib/seaborn.  
        Use 'df' e 'df_alocemp' para os DataFrames.  
        Sempre use plt.title(), plt.xlabel(), plt.ylabel() para rotular o gráfico."""  
    )  
]  
  
prompt = ChatPromptTemplate.from_messages([  
    ("system", system_prompt),  
    MessagesPlaceholder(variable_name="chat_history"),  
    ("user", "{input}"),  
    MessagesPlaceholder(variable_name="agent_scratchpad")  
])

# Isolar o agente e a memória no session_state para não vazar dados entre usuários
def inicializar_agente():
    if "agent_executor" not in st.session_state:
        llm = ChatOpenAI(  
            model="gpt-5.4-mini-2026-03-17",
            openai_api_key=api_key,  
        )  
        
        memory = ConversationBufferWindowMemory(  
            k=30,     
            memory_key="chat_history",  
            return_messages=True,
            output_key="output"
        )  
        
        agent = create_tool_calling_agent(llm, tools, prompt)  
        
        st.session_state.agent_executor = AgentExecutor(  
            agent=agent,  
            tools=tools,  
            memory=memory,  
            verbose=True,  
            handle_parsing_errors=True,  
            return_intermediate_steps=True  
        )

# Garante que o agente seja criado assim que o script rodar
inicializar_agente()
  
# --- FUNÇÃO PRINCIPAL DE PROCESSAMENTO ---  
  
def processar_pergunta(pergunta: str, chat_history: list = None) -> str:  
    global ultimo_grafico_base64  
    ultimo_grafico_base64 = None
      
    entrada = {"input": pergunta}  
    if chat_history:  
        entrada["chat_history"] = chat_history  
  
    try:  
        with get_openai_callback():  
            # Usa o agente isolado da sessão do usuário atual
            resposta_agente = st.session_state.agent_executor.invoke(entrada)  
  
        resposta_para_usuario = resposta_agente.get("output")  
          
        if ultimo_grafico_base64:  
            resposta_para_usuario += f"\\nGRAFICO_BASE64:{ultimo_grafico_base64}"  
            ultimo_grafico_base64 = None
  
    except Exception as e:  
        ultimo_grafico_base64 = None
        resposta_para_usuario = "Ocorreu um erro ao processar sua solicitação."  
        print(f"ERRO NO AGENTE: {e}")   
  
    return resposta_para_usuario  

# --- FRONT-END ---

# Sidebar
with st.sidebar:
    st.markdown(
        """
        <style>
        /* Cor de fundo da sidebar */
        [data-testid="stSidebar"] {
            background-color: #192E40;
        }
        
        /* Cor da fonte de todos os textos dentro da sidebar */
        [data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    st.image("logos/logo_pelt_branco.png", use_column_width=True) # Ajustado para use_column_width=True
    st.markdown("""
    <hr style="height:2px;border:none;color:#E6E6FA;background-color:#E6E6FA;" />
    """, unsafe_allow_html=True)
    
    st.markdown("### Bem-vindo!")
    st.markdown("Faça perguntas sobre a base de dados de empreendimentos do PELT.")
    
    st.markdown("""
    <hr style="height:2px;border:none;color:#E6E6FA;background-color:#E6E6FA;" />
    """, unsafe_allow_html=True)
    
    st.markdown("### Bases de dados")
    st.markdown("""
    **Dados Consolidados** - Status, viabilidade
    - CAPEX, OPEX, receita, TIRM
    - Notas: financeira, socioeconômica, estratégica
    - Rodovias e municípios associados
    
    **Demanda de Transporte** - Toneladas, TKU e veículos
    - Presente (2023) e projeção futura
    """)
    
    st.markdown("""
    <hr style="height:2px;border:none;color:#E6E6FA;background-color:#E6E6FA;" />
    """, unsafe_allow_html=True)
    
    st.markdown("### Exemplos de perguntas")
    st.markdown("""
    - *Quais são os empreendimentos rodoviários que estão em estudo?*
    - *Quais os valores de CAPEX dos empreendimentos da rodovia MG-050?*
    - *Compare demanda presente e futura do empreendimento BR-381?*
    - *Quais empreendimentos passam pelo município de Uberlândia?*
    """)

    st.markdown("""
    <hr style="height:2px;border:none;color:#E6E6FA;background-color:#E6E6FA;" />
    """, unsafe_allow_html=True)
    col_logo1, col_logo2 = st.columns(2, vertical_alignment="center")
    with col_logo1:
        st.image("logos/logo codemge - branco.png", use_column_width=True)
    with col_logo2:
        st.image("logos/logo govminas-branco.png", use_column_width=True)

# Área principal
st.markdown("<h1 style='text-align: center;'>Workshop Comercial</h1>", unsafe_allow_html=True)

tab_sobre, tab_chat = st.tabs(["📋 Sobre o PELT-MG", "💬 ChatPELT"])

# --- Funções auxiliares ---

def formatar_escala(valor):
    if valor >= 1e9:
        return f"{valor / 1e9:.1f}bi".replace('.', ',')
    elif valor >= 1e6:
        return f"{valor / 1e6:.1f}mi".replace('.', ',')
    elif valor >= 1e3:
        return f"{valor / 1e3:.1f}k".replace('.', ',')
    else:
        return f"{valor:.0f}"


# --- ABA: SOBRE O PELT-MG ---
with tab_sobre:
    st.markdown("""
    ## Plano Estadual de Logística e Transportes de Minas Gerais (PELT-MG)

    O **PELT-MG** é um instrumento de planejamento estratégico do Governo do Estado de Minas Gerais 
    que reúne estudos e análises sobre os **empreendimentos de infraestrutura de transportes** em todo o território mineiro.

    O plano abrange diversos modais — rodoviário, ferroviário, dutoviário, aeroviário e hidroviário — 
    e avalia cada empreendimento sob múltiplas dimensões: **viabilidade financeira, impacto socioeconômico, 
    demanda de transporte presente e futura, e relevância estratégica** para o desenvolvimento do estado.

    ###  Sobre este ChatBot

    O **ChatPELT** foi construído para facilitar a consulta e o entendimento da base de dados do PELT-MG.  
    Com ele, você pode:

    -  **Consultar empreendimentos** por viabilidade, status, fonte de financiamento, setor e outros critérios
    -  **Comparar dados financeiros** como CAPEX, OPEX, receita e TIR declarados
    -  **Analisar a demanda de transporte** presente (2023) e suas projeções futuras
    -  **Gerar gráficos** para visualizar tendências e distribuições
    -  **Entender as características** dos empreendimentos e da infraestrutura como um todo
    
    ---
    """)

    st.markdown("<h3 style='text-align: center;'>Visão geral dos empreendimentos</h3>", unsafe_allow_html=True)

    # Montar tabela de apresentação a partir do df consolidado
    try:        
        # Colunas sugerida pela Maíra 
        colunas_apresentacao = ['link_formulario','setor', 'id_empreendimento', 'nome_empreendimento', 'origem_ajustada',
                                'esfera_acao', 'descr_status_empreendimento', 'extensao_km', 'intervencao_principal',
                                'tipos_infraestruturas', 'ic_1_pond', 'impacto_avaliado_1_pond_cenario',
                                'capex', 'opex', 'receita', 'tirm', 'viabilidade', 'responsavel_gestao_infraestrutura', 
                                'municipio', 'natureza_empreendimento', 'Rodovias', 'regiao_geografica_intermediaria', 'grupo_modelagem']

        colunas_disponiveis = [c for c in colunas_apresentacao if c in df.columns]
        df_apresentacao = df[colunas_disponiveis].copy()
        
        df_apresentacao = df_apresentacao.rename(columns={
            'id_empreendimento': 'ID',
            'nome_empreendimento': 'Empreendimento',
            'origem_ajustada': 'Origem',
            'impacto_avaliado_1_pond_cenario': 'Impacto',
            'tipos_infraestruturas': 'Tipo Infraestrutura',
            'extensao_km': 'Extensao (Km)',
            'intervencao_principal': 'Intervenção Principal',
            'receita': 'Receita',
            'descr_status_empreendimento': 'Status',
            'natureza_empreendimento': 'Natureza',
            'setor': 'Setor',
            'viabilidade': 'Viabilidade',
            'tirm': 'TIRM',
            'capex': 'CAPEX (R$)',
            'opex': 'OPEX (R$)',
            'ic_1_pond': 'Nota Ponderada',
            'municipio': 'Município',
            'Rodovias': 'Rodovias',
            'esfera_acao': 'Esfera de Ação',
            'responsavel_gestao_infraestrutura': 'Responsável Gestão',
            'regiao_geografica_intermediaria' : 'Região intermediária',
            'grupo_modelagem': 'Grupo Modelagem'
        })

        # Métricas resumo
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total de empreendimentos", f"{len(df_apresentacao):,}".replace(",", "."))
        with col2:
            if 'Status' in df_apresentacao.columns:
                em_execucao = df_apresentacao['Status'].astype(str).str.contains('execução', case=False, na=False).sum()
            else:
                em_execucao = 0
            st.metric("Em execução", f"{em_execucao:,}".replace(",", "."))
        with col3:
            if 'Viabilidade' in df_apresentacao.columns:
                alta_viab = df_apresentacao['Viabilidade'].astype(str).str.contains('Alta', case=False, na=False).sum()
            else:
                alta_viab = 0
            st.metric("Alta viabilidade", f"{alta_viab:,}".replace(",", "."))
        with col4:
            esfera_estadual = (df['esfera_acao'].str.contains('Estadual', case=False, na=False)).sum() if 'esfera_acao' in df.columns else 0
            st.metric("Esfera estadual", f"{esfera_estadual:,}".replace(",", "."))
        
        st.markdown("---")

        # Filtros Categóricos
        def limpar_filtros():
            chaves = [
                'ms_setor', 'ms_status', 'ms_origem', 'ms_esfera', 'ms_impacto', 
                'ms_viab', 'ms_muns', 'ms_rods', 'ms_reg', 'sl_capex', 'sl_opex', 
                'sl_nota', 'ms_int', 'ms_nome'
            ]
            for chave in chaves:
                if chave in st.session_state:
                    if chave.startswith('ms_'):
                        st.session_state[chave] = []
                    else:
                        del st.session_state[chave]

        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        with col_filtro1:
            if 'Setor' in df_apresentacao.columns:
                setor_opcoes = sorted(df_apresentacao['Setor'].dropna().unique().tolist())
                filtro_setor = st.multiselect("Setor", setor_opcoes, key="ms_setor", placeholder="Escolha os setores...")
            else:
                filtro_setor = []
        
        with col_filtro2:
            if 'Status' in df_apresentacao.columns:
                status_opcoes = sorted(df_apresentacao['Status'].dropna().unique().tolist())
                filtro_status = st.multiselect("Status", status_opcoes, key="ms_status", placeholder="Escolha o status...")
            else:
                filtro_status = []
        
        with col_filtro3:
            if 'Origem' in df_apresentacao.columns:
                origem_opcoes = sorted(df_apresentacao['Origem'].dropna().unique().tolist())
                filtro_origem = st.multiselect("Origem", origem_opcoes, key="ms_origem", placeholder="Escolha a origem...")
            else:
                filtro_origem = []
        
        col_filtro4, col_filtro5, col_filtro6 = st.columns(3)
        
        with col_filtro4:
            if 'Esfera de Ação' in df_apresentacao.columns:
                esfera_opcoes = sorted(df_apresentacao['Esfera de Ação'].dropna().unique().tolist())
                filtro_esfera = st.multiselect("Esfera de Ação", esfera_opcoes, key="ms_esfera", placeholder="Escolha a esfera...")
            else:
                filtro_esfera = []
        
        with col_filtro5:
            if 'Impacto' in df_apresentacao.columns:
                impacto_opcoes = sorted(df_apresentacao['Impacto'].dropna().unique().tolist())
                filtro_impacto = st.multiselect("Impacto", impacto_opcoes, key="ms_impacto", placeholder="Escolha o impacto...")
            else:
                filtro_impacto = []
        
        with col_filtro6:
            if 'Viabilidade' in df_apresentacao.columns:
                viab_opcoes = sorted(df_apresentacao['Viabilidade'].dropna().unique().tolist())
                filtro_viab = st.multiselect("Viabilidade", viab_opcoes, key="ms_viab", placeholder="Escolha a viabilidade...")
            else:
                filtro_viab = []

        # Filtros Adicionais (Município e Rodovias)
        col_pesq1, col_pesq2, col_pesq3 = st.columns(3)
        with col_pesq1:
            if 'Município' in df_apresentacao.columns:
                municipios_unicos = sorted(df_apresentacao['Município'].explode().dropna().unique().tolist())
                filtro_muns = st.multiselect("Pesquisar Município", options=municipios_unicos, help="Comece a digitar para ver as opções...", key="ms_muns", placeholder="Busque municípios...")
            else:
                filtro_muns = []
                
        with col_pesq2:
            if 'Rodovias' in df_apresentacao.columns:
                rodovias_unicas = df_apresentacao['Rodovias'].explode().dropna().unique().tolist()
                rodovias_map = {}
                for r in rodovias_unicas:
                    r_str = str(r).strip()
                    match = re.match(r"^([A-Za-z]+)[-\s]*(\d+[A-Za-z]*)$", r_str)
                    if match:
                        p, n = match.group(1).upper(), match.group(2).upper()
                        rotulo = f"{p}-{n} ({p} {n}, {p}{n})"
                        rodovias_map[rotulo] = r
                    else:
                        rodovias_map[r_str] = r
                opcoes_rodovias = sorted(list(rodovias_map.keys()))
                filtro_rods_labels = st.multiselect("Pesquisar Rodovias", options=opcoes_rodovias, help="Ex: digite 'BR-381', 'br381' ou 'br 381'", key="ms_rods", placeholder="Busque rodovias...")
                filtro_rods = [rodovias_map[lbl] for lbl in filtro_rods_labels]
            else:
                filtro_rods = []
    
        with col_pesq3:
            if 'Região intermediária' in df_apresentacao.columns:
                regioes_unicas = sorted(df_apresentacao['Região intermediária'].explode().dropna().unique().tolist())
                filtro_reg = st.multiselect("Pesquisar Região", options=regioes_unicas, help="Comece a digitar para ver as opções...", key="ms_reg", placeholder="Busque regiões...")
            else:
                filtro_reg = []

        # Filtros Numéricos e Adicionais (Organizados em 2 linhas de 3 colunas)
        col_num1, col_num2, col_num3 = st.columns(3)
        col_filtro7, _, col_btn_limpar = st.columns(3)
        
        filtro_capex = None
        with col_num1:
            if 'CAPEX (R$)' in df_apresentacao.columns and not df_apresentacao['CAPEX (R$)'].isna().all():
                min_capex = float(df_apresentacao['CAPEX (R$)'].min())
                max_capex = float(df_apresentacao['CAPEX (R$)'].max())
                
                if min_capex < max_capex:
                    # Cria 100 "paradas" entre o valor mínimo e máximo
                    opcoes_capex = np.linspace(min_capex, max_capex, 200)
                    
                    filtro_capex = st.select_slider(
                        "CAPEX (R$)",
                        options=opcoes_capex,
                        value=(opcoes_capex[0], opcoes_capex[-1]),
                        format_func=formatar_escala,
                        key="sl_capex"
                    )
                    
        filtro_opex = None
        with col_num2:
            if 'OPEX (R$)' in df_apresentacao.columns and not df_apresentacao['OPEX (R$)'].isna().all():
                min_opex = float(df_apresentacao['OPEX (R$)'].min())
                max_opex = float(df_apresentacao['OPEX (R$)'].max())
                if min_opex < max_opex:
                    opcoes_opex = np.linspace(min_opex, max_opex, 100)

                    filtro_opex = st.select_slider(
                        "OPEX (R$)",
                        options=opcoes_opex,
                        value=(opcoes_opex[0],opcoes_opex[-1]),
                        format_func=formatar_escala,
                        key="sl_opex")

        filtro_nota = None
        with col_num3:
            if 'Nota Ponderada' in df_apresentacao.columns and not df_apresentacao['Nota Ponderada'].isna().all():
                min_nota = float(df_apresentacao['Nota Ponderada'].min())
                max_nota = float(df_apresentacao['Nota Ponderada'].max())
                if min_nota < max_nota:
                    filtro_nota = st.slider("Nota Ponderada", min_value=min_nota, max_value=max_nota, value=(min_nota, max_nota), format="%.2f", key="sl_nota")

        with col_filtro7:
            if 'Intervenção Principal' in df_apresentacao.columns:
                int_opcoes = sorted(df_apresentacao['Intervenção Principal'].dropna().unique().tolist())
                filtro_int = st.multiselect("Intervenção Principal", int_opcoes, key="ms_int", placeholder="Escolha a intervenção...")
            else:
                filtro_int = []

        with col_btn_limpar:
            # Espaçador para alinhar o botão com o campo acima
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            st.button("REINICIAR FILTROS", on_click=limpar_filtros, use_container_width=True)

        st.markdown("---")
        if 'Empreendimento' in df_apresentacao.columns:
            opcoes_empreendimentos = sorted(df_apresentacao['Empreendimento'].dropna().unique().tolist())
        else:
            opcoes_empreendimentos = []

        filtro_texto_nome = st.multiselect(
            "Pesquisar por Nome do Empreendimento", 
            options=opcoes_empreendimentos,
            placeholder="Digite parte do nome para buscar...",
            key="ms_nome"
        )

        # Aplicação dos Filtros
        df_filtrado = df_apresentacao.copy()

        # Filtros Categóricos 
        if filtro_viab and 'Viabilidade' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Viabilidade'].isin(filtro_viab)]
            
        if filtro_status and 'Status' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Status'].isin(filtro_status)]
            
        if filtro_origem and 'Origem' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Origem'].isin(filtro_origem)]
            
        if filtro_setor and 'Setor' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Setor'].isin(filtro_setor)]
            
        if filtro_esfera and 'Esfera de Ação' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Esfera de Ação'].isin(filtro_esfera)]
            
        if filtro_impacto and 'Impacto' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Impacto'].isin(filtro_impacto)]
            
        if filtro_int and 'Intervenção Principal' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Intervenção Principal'].isin(filtro_int)]

        if filtro_muns and 'Município' in df_filtrado.columns:
            def has_mun(val):
                if isinstance(val, (list, np.ndarray)):
                    return any(m in val for m in filtro_muns)
                return val in filtro_muns
            df_filtrado = df_filtrado[df_filtrado['Município'].apply(has_mun)]
            
        if filtro_rods and 'Rodovias' in df_filtrado.columns:
            def has_rod(val):
                if isinstance(val, (list, np.ndarray)):
                    return any(r in val for r in filtro_rods)
                return val in filtro_rods
            df_filtrado = df_filtrado[df_filtrado['Rodovias'].apply(has_rod)]
            
        if filtro_capex:
            df_filtrado = df_filtrado[df_filtrado['CAPEX (R$)'].isna() | df_filtrado['CAPEX (R$)'].between(filtro_capex[0], filtro_capex[1])]
        if filtro_opex:
            df_filtrado = df_filtrado[df_filtrado['OPEX (R$)'].isna() | df_filtrado['OPEX (R$)'].between(filtro_opex[0], filtro_opex[1])]
        if filtro_nota:
            df_filtrado = df_filtrado[df_filtrado['Nota Ponderada'].isna() | df_filtrado['Nota Ponderada'].between(filtro_nota[0], filtro_nota[1])]
            
        if filtro_texto_nome and 'Empreendimento' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Empreendimento'].isin(filtro_texto_nome)]
        
        st.markdown(f"**Exibindo {len(df_filtrado)} empreendimentos**")
        #st.dataframe(df_filtrado, use_container_width=True, height=500, hide_index=True)

        st.dataframe(
            df_filtrado, 
            use_container_width=True, 
            height=500, 
            hide_index=True,
            column_config={
                # Configura a coluna do link para ser um botão clicável
                "link_formulario": st.column_config.LinkColumn(
                    "Ação", 
                    display_text="🔗 Avaliar", 
                    help="Clique para abrir o formulário"
                ),
                # Formatação unidades
                "CAPEX (R$)": st.column_config.NumberColumn(
                    format="%.0f" 
                ),
                "OPEX (R$)": st.column_config.NumberColumn(
                    format="%.0f"
                ),
                "Extensao (Km)": st.column_config.NumberColumn(
                    format="%.0f"
                ),
                "Receita": st.column_config.NumberColumn(
                    format="%.0f"
                )
            }
        )

    except Exception as e:
        st.error(f"Erro ao montar tabela de apresentação: {e}")

# --- ABA: CHATPELT ---

if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "Como posso ajudar você?"}]
if "processing" not in st.session_state:
    st.session_state["processing"] = False

def corrigir_formatacao_moeda(texto):  
    texto = re.sub(r'R(\d+,\d+)', r'R$ \1', texto)  
    texto = re.sub(r'R (\d+,\d+)', r'R$ \1', texto)  
    return texto  

def exibir_mensagem(content):    
    if "GRAFICO_BASE64:" in content:    
        partes = content.split("GRAFICO_BASE64:")    
        texto = partes[0].strip()    
        texto = re.sub(r'\\n$', '', texto).strip()  
  
        if texto:    
            texto_corrigido = corrigir_formatacao_moeda(texto)    
            st.write(texto_corrigido) 
          
        try:  
            base64_data = partes[1].strip()  
            img_data = base64.b64decode(base64_data)  
            st.image(img_data, use_column_width=True)  
        except Exception as e:  
            st.error(f"Erro ao exibir gráfico: {e}")  
    else:  
        content_corrigido = corrigir_formatacao_moeda(content)  
        st.write(content_corrigido)

with tab_chat:
    mensagens_container = st.container()
    
    with mensagens_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                exibir_mensagem(msg["content"])

    if prompt := st.chat_input("Digite sua pergunta...", disabled=st.session_state.processing):
        st.session_state.processing = True
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with mensagens_container:
            with st.chat_message("user"):
                st.write(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("Analisando..."):
                    resposta = processar_pergunta(prompt)
                    exibir_mensagem(resposta)
        
        st.session_state.messages.append({"role": "assistant", "content": resposta})
        st.session_state.processing = False
        st.rerun()