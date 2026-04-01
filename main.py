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
from langchain.memory import ConversationTokenBufferMemory 
from langchain_community.callbacks import get_openai_callback  
  
from dotenv import load_dotenv  
from pathlib import Path  
import os

st.set_page_config(
    page_title="ChatPELT", 
    page_icon="🏢",
    layout="wide"
)
  
ultimo_grafico_base64 = None

# --- CONFIGURAÇÃO INICIAL ---

#dotenv_path = Path(__file__).resolve().parent / '.env'
#load_dotenv(dotenv_path)
#api_key = os.getenv("OPENAI_API_KEY")
api_key = st.secrets["OPENAI_API_KEY"]

  
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
        
        memory = ConversationTokenBufferMemory(  
            llm=llm,                 
            max_token_limit=10000,     
            memory_key="chat_history",  
            return_messages=True  
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
        [data-testid="stSidebar"] {
            background-color: #BAD6D9;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    st.image("logos/logo peltmg vermelho.png", width='stretch') # Ajustado de stretch para auto
    st.markdown("---")
    
    st.markdown("### Bem-vindo!")
    st.markdown("Faça perguntas sobre a base de dados de empreendimentos do PELT.")
    
    st.markdown("---")
    
    st.markdown("### Bases de dados")
    st.markdown("""
    **Dados Consolidados** - Status, viabilidade, rentabilidade
    - CAPEX, OPEX, receita, TIRM
    - Notas: financeira, socioeconômica, estratégica
    - Rodovias e municípios associados
    
    **Demanda de Transporte** - Toneladas, TKU e veículos
    - Presente (2023) e projeção futura
    """)
    
    st.markdown("---")
    
    st.markdown("### Exemplos de perguntas")
    st.markdown("""
    - *Quais são os empreendimentos rodoviários que estão em estudo?*
    - *Quais os valores de CAPEX dos empreendimentos da rodovia MG-050?*
    - *Compare demanda presente e futura do empreendimento BR-381?*
    - *Quais empreendimentos passam pelo município de Uberlândia?*
    """)

    st.markdown("---")
    col_logo1, col_logo2 = st.columns(2, vertical_alignment="center")
    with col_logo1:
        st.image("logos/logo codemge - branco.png", width='stretch')
    with col_logo2:
        st.image("logos/logo govminas-branco.png", width='stretch')

# Área principal
st.markdown("<h1 style='text-align: center;'>Workshop Comercial</h1>", unsafe_allow_html=True)

tab_sobre, tab_chat = st.tabs(["📋 Sobre o PELT-MG", "💬 ChatPELT"])

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

    ###  Visão geral dos empreendimentos
    """)

    # Montar tabela de apresentação a partir do df consolidado
    try:
        colunas_apresentacao = ['id_empreendimento', 'nome_empreendimento', 'descr_status_empreendimento', 
                                'natureza_empreendimento', 'viabilidade', 'rentabilidade',
                                'capex', 'opex', 'tirm', 'ic_1_pond', 'municipio', 'Rodovias',
                                'setor', 'esfera_acao', 'responsavel_gestao_infraestrutura', 'regiao_geografica_intermediaria' ]
        colunas_disponiveis = [c for c in colunas_apresentacao if c in df.columns]
        df_apresentacao = df[colunas_disponiveis].copy()
        
        df_apresentacao = df_apresentacao.rename(columns={
            'id_empreendimento': 'ID',
            'nome_empreendimento': 'Empreendimento',
            'descr_status_empreendimento': 'Status',
            'natureza_empreendimento': 'Natureza',
            'viabilidade': 'Viabilidade',
            'rentabilidade': 'Rentabilidade',
            'tirm': 'TIRM',
            'capex': 'CAPEX (R$)',
            'opex': 'OPEX (R$)',
            'ic_1_pond': 'Nota Ponderada',
            'municipio': 'Município',
            'Rodovias': 'Rodovias',
            'setor': 'Setor',
            'esfera_acao': 'Esfera de Ação',
            'responsavel_gestao_infraestrutura': 'Responsável Gestão',
            'regiao_geografica_intermediaria' : 'Região intermediária'
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
        col_filtro1, col_filtro2, col_filtro3 = st.columns(3)
        with col_filtro1:
            if 'Viabilidade' in df_apresentacao.columns:
                viab_opcoes = ['Todos'] + sorted(df_apresentacao['Viabilidade'].dropna().unique().tolist())
            else:
                viab_opcoes = ['Todos']
            filtro_viab = st.selectbox("Viabilidade", viab_opcoes)
        with col_filtro2:
            if 'Status' in df_apresentacao.columns:
                status_opcoes = ['Todos'] + sorted(df_apresentacao['Status'].dropna().unique().tolist())
            else:
                status_opcoes = ['Todos']
            filtro_status = st.selectbox("Status", status_opcoes)
        with col_filtro3:
            if 'Natureza' in df_apresentacao.columns:
                nat_opcoes = ['Todos'] + sorted(df_apresentacao['Natureza'].dropna().unique().tolist())
            else:
                nat_opcoes = ['Todos']
            filtro_nat = st.selectbox("Natureza", nat_opcoes)

        col_filtro4, col_filtro5, col_filtro6 = st.columns(3)
        with col_filtro4:
            if 'Setor' in df_apresentacao.columns:
                setor_opcoes = ['Todos'] + sorted(df_apresentacao['Setor'].dropna().unique().tolist())
                filtro_setor = st.selectbox("Setor", setor_opcoes)
            else:
                filtro_setor = 'Todos'
        with col_filtro5:
            if 'Esfera de Ação' in df_apresentacao.columns:
                esfera_opcoes = ['Todos'] + sorted(df_apresentacao['Esfera de Ação'].dropna().unique().tolist())
                filtro_esfera = st.selectbox("Esfera de Ação", esfera_opcoes)
            else:
                filtro_esfera = 'Todos'
        with col_filtro6:
            if 'Responsável Gestão' in df_apresentacao.columns:
                resp_opcoes = ['Todos'] + sorted(df_apresentacao['Responsável Gestão'].dropna().unique().tolist())
                filtro_resp = st.selectbox("Responsável Gestão", resp_opcoes)
            else:
                filtro_resp = 'Todos'

        # Filtros Adicionais (Município e Rodovias)
        col_pesq1, col_pesq2, col_pesq3 = st.columns(3)
        with col_pesq1:
            if 'Município' in df_apresentacao.columns:
                municipios_unicos = sorted(df_apresentacao['Município'].explode().dropna().unique().tolist())
                filtro_muns = st.multiselect("Pesquisar Município", options=municipios_unicos, help="Comece a digitar para ver as opções...")
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
                filtro_rods_labels = st.multiselect("Pesquisar Rodovias", options=opcoes_rodovias, help="Ex: digite 'BR-381', 'br381' ou 'br 381'")
                filtro_rods = [rodovias_map[lbl] for lbl in filtro_rods_labels]
            else:
                filtro_rods = []
    
            with col_pesq3:
                if 'Região intermediária' in df_apresentacao.columns:
                    municipios_unicos = sorted(df_apresentacao['Região intermediária'].explode().dropna().unique().tolist())
                    filtro_muns = st.multiselect("Pesquisar Região", options=municipios_unicos, help="Comece a digitar para ver as opções...")
                else:
                    filtro_muns = []

        # Filtros Numéricos
        col_num1, col_num2, col_num3 = st.columns(3)
        
        filtro_capex = None
        with col_num1:
            if 'CAPEX (R$)' in df_apresentacao.columns and not df_apresentacao['CAPEX (R$)'].isna().all():
                min_capex = float(df_apresentacao['CAPEX (R$)'].min())
                max_capex = float(df_apresentacao['CAPEX (R$)'].max())
                if min_capex < max_capex:
                    filtro_capex = st.slider("CAPEX (R$)", min_value=min_capex, max_value=max_capex, value=(min_capex, max_capex), format="R$ %.0f")
                    
        filtro_opex = None
        with col_num2:
            if 'OPEX (R$)' in df_apresentacao.columns and not df_apresentacao['OPEX (R$)'].isna().all():
                min_opex = float(df_apresentacao['OPEX (R$)'].min())
                max_opex = float(df_apresentacao['OPEX (R$)'].max())
                if min_opex < max_opex:
                    filtro_opex = st.slider("OPEX (R$)", min_value=min_opex, max_value=max_opex, value=(min_opex, max_opex), format="R$ %.0f")

        filtro_nota = None
        with col_num3:
            if 'Nota Ponderada' in df_apresentacao.columns and not df_apresentacao['Nota Ponderada'].isna().all():
                min_nota = float(df_apresentacao['Nota Ponderada'].min())
                max_nota = float(df_apresentacao['Nota Ponderada'].max())
                if min_nota < max_nota:
                    filtro_nota = st.slider("Nota Ponderada", min_value=min_nota, max_value=max_nota, value=(min_nota, max_nota), format="%.2f")

        # Aplicação dos Filtros
        df_filtrado = df_apresentacao.copy()
        
        if filtro_viab != 'Todos' and 'Viabilidade' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Viabilidade'] == filtro_viab]
        if filtro_status != 'Todos' and 'Status' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Status'] == filtro_status]
        if filtro_nat != 'Todos' and 'Natureza' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Natureza'] == filtro_nat]
        if filtro_setor != 'Todos' and 'Setor' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Setor'] == filtro_setor]
        if filtro_esfera != 'Todos' and 'Esfera de Ação' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Esfera de Ação'] == filtro_esfera]
        if filtro_resp != 'Todos' and 'Responsável Gestão' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Responsável Gestão'] == filtro_resp]
            
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
        
        st.markdown(f"**Exibindo {len(df_filtrado)} empreendimentos**")
        st.dataframe(df_filtrado, width='stretch', height=500)

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
            st.image(img_data, width='stretch')  
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