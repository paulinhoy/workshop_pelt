import pandas as pd
import re

# --- Carregar dados ---
df_empreendimento = pd.read_json("dadospelt/empreendimento.json")
df_empreendimento = pd.json_normalize(df_empreendimento['empreendimento'])

df_impacto = pd.read_json("dadospelt/mvw_4_calcula_impacto_1_pond_cenario.json")
df_impacto = pd.json_normalize(df_impacto['mvw_4_calcula_impacto_1_pond_cenario'])

df_extmuni = pd.read_json("dadospelt/mvw_empreendimento_municipio_extensao.json")
df_extmuni = pd.json_normalize(df_extmuni['mvw_empreendimento_municipio_extensao'])
df_extmuni = df_extmuni[['id_empreendimento', 'id_municipio']]

df_muni = pd.read_json("dadospelt/tbr_municipio.json")
df_muni = pd.json_normalize(df_muni['tbr_municipio'])
df_muni = df_muni[['int_idmunicipio', 'vhr_municipio']]

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

df_rodovias['Rodovias'] = df_rodovias['Rodovias'].apply(padronizar_lista_rodovias)
df_rodovias = df_rodovias[['id_empreendimento', 'Rodovias']]

# Juntar rodovias com municipios (ambos por id_empreendimento)
df_municipio = pd.merge(df_municipio, df_rodovias, on='id_empreendimento', how='outer')

# --- Selecionar colunas ---
df_empreendimento_cols = df_empreendimento[['id_empreendimento', 'capex_declarado', 'opex_declarado', 'receita_declarada', 'tir_declarada', '']]

df_impacto_cols = df_impacto[['id_empreendimento', 'nome_empreendimento', 'setor',
                               'descr_status_empreendimento', 'natureza_empreendimento',
                               'esfera_acao', 'grupo_modelagem',
                               'responsavel_gestao_infraestrutura', 'rentabilidade', 'tirm', 'viabilidade',
                               'dimensao_financeira', 'dimensao_socioeconomica_pond', 'dimensao_estrategica', 'ic_1_pond']]


df_consolidado = pd.merge(df_empreendimento_cols, df_impacto_cols, on='id_empreendimento', how='inner')

# Juntar com municipios e rodovias
df_consolidado = pd.merge(df_consolidado, df_municipio, on='id_empreendimento', how='left')

# Verificação
nulos_nome = df_consolidado['nome_empreendimento'].isna().sum()
total = len(df_consolidado)
print(f"Total de empreendimentos: {total}")
print(f"Nulos em nome_empreendimento: {nulos_nome}")
print(f"Colunas: {list(df_consolidado.columns)}")

# Salvar
df_consolidado.to_parquet('dados_consolidados.parquet')
print("\nArquivo dados_consolidados.parquet salvo com sucesso!")
