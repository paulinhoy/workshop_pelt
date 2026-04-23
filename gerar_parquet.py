import pandas as pd
import re
import numpy as np

# --- Carregar dados ---
df_empreendimento = pd.read_json("dadospelt/vw_empreendimento.json")
df_empreendimento = pd.json_normalize(df_empreendimento['vw_empreendimento'])

# Empreendimento id=1994
df1994 = pd.read_json('dadospelt/mvw_atlas_comercial_emp1994.json')
df1994 = pd.json_normalize(df1994['mvw_atlas_comercial_emp1994'])
df_emp1994 = df1994[['id_empreendimento', 'origem_ajustada', 'nome_empreendimento', 'setor',
                    'descr_status_empreendimento', 'natureza_empreendimento', 'esfera_acao',
                    'grupo_modelagem', 'responsavel_gestao_infraestrutura', 'tirm',
                    'viabilidade', 'ic_1_pond', 'CAPEX', 'OPEX', 'receita']]
df_emp1994.rename(columns={'CAPEX': 'capex', 'OPEX': 'opex'},inplace=True)

df_impacto = pd.read_json("dadospelt/mvw_4_calcula_impacto_1_pond_cenario.json")
df_impacto = pd.json_normalize(df_impacto['mvw_4_calcula_impacto_1_pond_cenario'])

df_extmuni = pd.read_json("dadospelt/mvw_empreendimento_municipio_extensao.json")
df_extmuni = pd.json_normalize(df_extmuni['mvw_empreendimento_municipio_extensao'])
df_extmuni = df_extmuni[['id_empreendimento', 'id_municipio']]

df_muni = pd.read_json("dadospelt/tbr_municipio.json")
df_muni = pd.json_normalize(df_muni['tbr_municipio'])
df_muni = df_muni[['int_idmunicipio', 'vhr_municipio']]

df_gestao_carteiras = pd.read_json("dadospelt/vw_gestao_carteiras.json")
df_gestao_carteiras = pd.json_normalize(df_gestao_carteiras['vw_gestao_carteiras'])
df_gestao_carteiras = df_gestao_carteiras[['id_empreendimento', 'impacto_avaliado_1_pond_cenario', 'receita']]

df_extensao = pd.read_json("dadospelt/mvw_geo_extensao.json")
df_extensao = pd.json_normalize(df_extensao['mvw_geo_extensao'])
df_extensao['extensao_km'] = pd.to_numeric(df_extensao['extensao_km'], errors='coerce')
df_extensao['extensao_km'] = df_extensao['extensao_km'].replace([np.inf, -np.inf], np.nan)
df_extensao['extensao_km'] = df_extensao['extensao_km'].round()
df_extensao['extensao_km'] = df_extensao['extensao_km'].astype('Int64')

# --- Carteira classificada ---
df_classificada = pd.read_json('dadospelt/vw_carteira_classificada.json')
df_classificada = pd.json_normalize(df_classificada['vw_carteira_classificada'])
df_classificada = df_classificada[['id_empreendimento']]
df_classificada['carteira_classificada'] = 1

# --- Dados Capex e Opex por empreendimento
df_economico = pd.read_json('dadospelt/vw_empreendimento_custo_economico_lp.json')
df_economico = pd.json_normalize(df_economico['vw_empreendimento_custo_economico_lp'])
df_economico = df_economico[['id_empreendimento','capex_empreendimento_atualizado', 'opex_empreendimento_atualizado']]

# --- Regiões intermediarias ---
df_rgi = pd.read_json('dadospelt/vw_agregacao_municipio.json')
df_rgi = pd.json_normalize(df_rgi['vw_agregacao_municipio'])
df_rgi = df_rgi[['id_rgint', 'regiao_reografica_intermediaria']]
df_rgi = df_rgi.groupby('id_rgint')['regiao_reografica_intermediaria'].first().reset_index()

df_region_emp = pd.read_json('dadospelt/vw_empreendimento_rgint.json')
df_region_emp = pd.json_normalize(df_region_emp['vw_empreendimento_rgint'])
df_region_emp = df_region_emp[['id_empreendimento', 'id_rgint']]

df_region = pd.merge(df_region_emp, df_rgi, on='id_rgint', how='left')

df_region.rename(columns={'regiao_reografica_intermediaria': 'regiao_geografica_intermediaria'}, inplace=True)
df_region = df_region.groupby('id_empreendimento')['regiao_geografica_intermediaria'].agg(list).reset_index()

# --- Links do formulário para empreendimento ---
df_links = pd.read_csv("links_formulario.csv")

# --- Municipios por empreendimento ---
df_municipio = pd.merge(df_extmuni, df_muni, left_on='id_municipio', right_on='int_idmunicipio', how='left')[['id_empreendimento','vhr_municipio']]
df_municipio = df_municipio.groupby('id_empreendimento')['vhr_municipio'].agg(lambda x: list(set(x))).reset_index()
df_municipio.rename(columns={'vhr_municipio': 'municipio'}, inplace=True)


df_rodovias = df_empreendimento[['id_empreendimento', 'nome_empreendimento']].copy()
df_rodovias['Rodovias'] = df_rodovias['nome_empreendimento'].str.findall(r'\b(?:BR|MG|MGC|AMG|MGT|LMG|CMG)[\s\-/]+\d{3,4}\b')

def padronizar_lista_rodovias(lista_rodovias):
    if not isinstance(lista_rodovias, list):
        return lista_rodovias
    lista_limpa = []
    for rodovia in lista_rodovias:
        rodovia = rodovia.upper()
        rodovia_padronizada = re.sub(r'[\s\-/]+', '-', rodovia)
        lista_limpa.append(rodovia_padronizada)
    return list(set(lista_limpa))

def converter_para_lista(texto):
    if pd.isna(texto) or texto == '{}':
        return []
    # Busca tudo o que está dentro de aspas duplas " "
    return re.findall(r'"([^"]*)"', texto)

df_rodovias['Rodovias'] = df_rodovias['Rodovias'].apply(padronizar_lista_rodovias)
df_rodovias = df_rodovias[['id_empreendimento', 'Rodovias']]

# Juntar rodovias com municipios (ambos por id_empreendimento)
df_municipio = pd.merge(df_municipio, df_rodovias, on='id_empreendimento', how='outer')

# --- Selecionar colunas ---
df_empreendimento_cols = df_empreendimento[['id_empreendimento', 'origem_ajustada', 'tipos_infraestruturas','intervencao_principal', 'nome_empreendimento']]

df_impacto_cols = df_impacto[['id_empreendimento', 'setor','descr_status_empreendimento', 'natureza_empreendimento',
                               'esfera_acao', 'grupo_modelagem', 'responsavel_gestao_infraestrutura', 
                               'tirm', 'viabilidade', 'dimensao_financeira',
                               'dimensao_socioeconomica_pond', 'dimensao_estrategica', 'ic_1_pond']]


df_consolidado = pd.merge(df_empreendimento_cols, df_impacto_cols, on='id_empreendimento', how='inner')

# Juntar com municipios e rodovias
df_consolidado = pd.merge(df_consolidado, df_municipio, on='id_empreendimento', how='left')


# Consolidando dados de capex, opex, carteira_classificada, regiões intermediarias e alteracao nomes da colunas
df_consolidado = pd.merge(df_consolidado, df_economico, on='id_empreendimento',how='left')
df_consolidado = pd.merge(df_consolidado, df_classificada, on='id_empreendimento', how='left')
df_consolidado['carteira_classificada'].fillna(0, inplace=True)
df_consolidado.rename(columns={'capex_empreendimento_atualizado': 'capex', 'opex_empreendimento_atualizado' : 'opex'}, inplace=True)
df_consolidado = pd.merge(df_consolidado, df_region, on='id_empreendimento', how='left')
df_consolidado= pd.merge(df_consolidado, df_extensao, on='id_empreendimento', how='left')
df_consolidado=pd.merge(df_consolidado, df_gestao_carteiras, on='id_empreendimento', how='left')
df_consolidado['tipos_infraestruturas'] = df_consolidado['tipos_infraestruturas'].apply(converter_para_lista)

#Adicionando empreendimento id=1994
df_consolidado = pd.concat([df_consolidado, df_emp1994], ignore_index=True)

# Juntar com link para cada empreendimento
df_consolidado = pd.merge(df_consolidado, df_links, on ='id_empreendimento', how='inner')

# Verificação
nulos_nome = df_consolidado['nome_empreendimento'].isna().sum()
total = len(df_consolidado)
print(f"Total de empreendimentos: {total}")
print(f"Nulos em nome_empreendimento: {nulos_nome}")
print(f"Colunas: {list(df_consolidado.columns)}")

# Salvar
df_consolidado.to_parquet('dados_consolidados.parquet')
df_consolidado.to_csv('dados_consolidados.csv')

print("\nArquivo dados_consolidados.parquet salvo com sucesso!")