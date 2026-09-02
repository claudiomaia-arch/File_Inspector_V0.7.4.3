# CAD / Usinagem Inspector — V0.5.0
## Persistência e Auditoria Confiável

Esta versão é a fundação de persistência do Inspector. A partir dela, **a aplicação e os dados corporativos ficam separados**.

## O que muda

### 1. Banco persistente fora da pasta da versão
Os dados passam a ficar, por padrão, em:

```text
C:\Users\<USUARIO>\CAD_Usinagem_Inspector_DATA\
├── inspector.db
├── backups\
└── logs\
```

Isso significa que futuras versões (V0.6, V0.7...) podem ser extraídas em novas pastas e continuar utilizando o mesmo banco.

### 2. Migração do banco da V0.4.x
Para trazer usuários, pasta oficial, validações e auditoria existentes:

1. Extraia a V0.5 em uma pasta nova.
2. Execute `install.bat`.
3. Execute `migrate_data_from_previous_version.bat`.
4. Informe o caminho da pasta da versão antiga.
5. Depois execute `run.bat`.

Na primeira inicialização, a V0.5 converte o banco automaticamente para o schema novo.

### 3. Backup antes de migração
Se já existir um banco persistente e houver mudança de schema, uma cópia é criada automaticamente em `backups`.

### 4. Validações imutáveis
A V0.5 não substitui uma validação anterior. Cada validação gera um novo evento com:
- usuário;
- pasta;
- assinatura do estado;
- justificativa;
- data/hora;
- versão do Inspector.

### 5. Evidências de alteração dos arquivos
Durante a análise, os arquivos monitorados recebem SHA-256.

O sistema registra eventos imutáveis quando detectar:
- arquivo adicionado;
- arquivo alterado;
- arquivo removido.

O estado atual fica separado do histórico.

### 6. Nova área “Evidências”
O menu corporativo mostra o histórico das alterações detectadas.

## Importante sobre a primeira análise
Na primeira análise da V0.5, todos os arquivos existentes ainda não conhecidos pelo banco serão registrados como `ARQUIVO_ADICIONADO`. A partir das análises seguintes, alterações reais de conteúdo serão registradas como `ARQUIVO_ALTERADO`.

## Recursos preservados
A V0.5 mantém:
- login e cadastro;
- recuperação de senha por link;
- cabeçalho fixo;
- ambiente corporativo;
- envolvidos;
- histórico;
- auditoria;
- regras consolidadas de Usinagem Interna da linha V0.4.x.

## Segurança
O Inspector continua sem alterar STEP, PDF, SLDPRT, SLDDRW ou NC. O histórico e o banco são os únicos dados escritos pelo sistema.

## Próxima etapa planejada
Após validar a persistência da V0.5:
- V0.6: Corte a Laser;
- V0.7: Estrutura do Produto.

## V0.6.0 — Corte a Laser

- Novo processo independente com pasta oficial própria.
- Todas as subpastas são avaliadas.
- Código válido: `CRT######`.
- Pastas `USI######` ou `PRE######` dentro do Corte a Laser geram alerta.
- Arquivo `.DXF` obrigatório.
- Datasheet `.PDF` obrigatório.
- Nome da pasta deve conter somente código(s) CRT.
- Alterações de DXF/PDF entram no histórico persistente de evidências.
- Estrutura do Produto permanece fora do escopo desta versão.


## V0.6.1 — Correção de arquitetura e configuração
- Produto renomeado para **File Inspector**.
- Usinagem Interna e Corte a Laser passam a ser apresentados como processos equivalentes.
- Cabeçalho deixa de permanecer preso a "Usinagem Interna".
- Tela de Corte a Laser mostra o caminho atualmente configurado.
- Configuração de pasta revisada: o caminho é colado a partir do Explorador do Windows.
- Mensagem explícita quando o caminho não é acessível pelo computador servidor.
- Retorno automático à tela de Corte a Laser após salvar.
- Mantida toda a persistência, auditoria e evidências das versões anteriores.


## V0.6.2.2.2 — Arquitetura Multiprocesso + correção da pasta de Corte
- Corrigido o motivo de o botão **Configurar / alterar pasta** do Corte a Laser não abrir: o modal estava fora do bloco Jinja renderizado.
- O modal agora é renderizado corretamente dentro da aplicação.
- Visão Geral mostra **Processos monitorados** em vez de uma única "Pasta oficial".
- Usinagem Interna e Corte a Laser aparecem como processos equivalentes.
- Cabeçalho passa a acompanhar a tela: File Inspector / Usinagem Interna / Corte a Laser.
- Corrigida regressão de persistência: validações voltam a ser gravadas como eventos imutáveis em `validation_events`.
- Mantidos banco persistente, evidências, auditoria e recuperação de senha.


## V0.6.2.2.2 — Correção do configurador de Corte a Laser
- Corrigido o botão `Configurar / alterar` do Corte a Laser.
- O modal agora é inserido uma única vez dentro do bloco renderizado do template.
- Botões usam `type="button"` para evitar submit acidental.
- Nova função `openLaserModal()` faz abertura robusta e exibe diagnóstico se o modal não for carregado.
- Mantidas todas as regras e a persistência da V0.6.2.2.


## V0.6.2.2 — Configurador multiprocesso unificado
- Removidos os modais separados de Usinagem e Corte a Laser.
- Um único modal `process-modal` configura qualquer processo.
- `Usinagem Interna` e `Corte a Laser` usam o mesmo fluxo de configuração.
- O modal carrega automaticamente o caminho atual do processo.
- O endpoint `/process-environment` agora salva tanto Usinagem quanto Corte.
- O caminho de Usinagem permanece sincronizado com a configuração legada `corporate_settings`.
- Depois de salvar, o sistema retorna para o processo configurado.
- Corrigido o problema em que o botão do Corte chamava uma janela inexistente.


## V0.6.2.3 — Configuração de pastas refeita
- Removido o modal nativo anterior.
- Usinagem Interna e Corte a Laser usam painéis de configuração sempre presentes no HTML.
- Caminho já existente da Usinagem pode ser substituído normalmente.
- Corte a Laser usa o mesmo endpoint e persistência.
- O novo caminho precisa existir no computador servidor.


## V0.6.2.4 — Correção do erro Jinja
- Corrigido `jinja2.exceptions.UndefinedError: 'laser_path_global' is undefined`.
- O caminho do Corte a Laser agora é calculado no backend Python e enviado ao template como `laser_path`.
- Removida a dependência de `namespace()` no template.
- Mantidos os painéis próprios de configuração de Usinagem e Corte a Laser.
- Atualizado o título base para `File Inspector`.

## V0.6.2.5 — Correção definitiva dos painéis de configuração
- Corrigido o erro estrutural do template: os painéis de Usinagem e Corte estavam dentro do bloco `<title>`.
- Os dois painéis agora ficam dentro do corpo real da página.
- Incluído fallback JavaScript no próprio template para evitar interferência de cache do `app.js`.
- Usinagem e Corte continuam usando a mesma rota de salvamento multiprocesso.


## V0.6.3.0 — Padronização dos monitoramentos e dashboard por processo
- Usinagem Interna e Corte a Laser passam a seguir o mesmo padrão visual de monitoramento.
- Corte a Laser recebe filtro por status e campo de busca.
- Mantido cabeçalho fixo da tabela.
- Visão Geral passa a separar indicadores de Usinagem e Corte a Laser.
- Cada processo exibe: pastas analisadas, conformes, atenção/verificadas e incompletas.
- Os botões de análise e configuração permanecem independentes por processo.


## V0.6.3.1 — Indicadores persistentes e layout padronizado
- Corrigidos os indicadores da Visão Geral para Usinagem e Corte a Laser.
- O resumo de cada análise agora é salvo no banco por processo e permanece após trocar de tela ou recarregar.
- Usinagem Interna e Corte a Laser passam a ter o mesmo padrão de página: identificação do processo, pasta configurada, botão de configuração, filtro, busca e botão de análise.
- Mantidas as colunas específicas de cada processo.


## V0.6.3.2 — Correção robusta dos indicadores da Visão Geral
- A Visão Geral passa a buscar os indicadores diretamente do banco toda vez que é aberta.
- Criado `/api/process-summaries` para retornar os últimos resultados de Usinagem e Corte.
- A análise de Usinagem atualiza os cards imediatamente no navegador e também persiste no banco.
- A análise de Corte mantém o mesmo comportamento.
- CSS e JavaScript agora usam versionamento na URL para impedir que o navegador reutilize arquivos antigos em cache.


## V0.7.0 — Estrutura do Produto
- Novo módulo `Estrutura do Produto`.
- Upload de PDF e imagens/prints.
- PDF textual é lido automaticamente.
- Imagens são aceitas; nesta versão podem receber texto/transcrição complementar para a identificação dos códigos.
- Identificação de USI, CRT e PRE.
- Regra `03 = interno`; `01 = externo`.
- USI03: classificado para avaliação em Usinagem.
- CRT03: classificado para avaliação em Corte a Laser.
- USI01/CRT01: identificados como externos e fora da avaliação atual.
- PRE: classificado como Preparados e exibido, sem avaliação de PRE/Roteiros nesta versão.
- Histórico das estruturas e itens fica persistido no banco.
- V0.7 apenas entende/classifica a estrutura; o cruzamento automático com as pastas monitoradas permanece reservado para V0.8.


## V0.7.1 — Primeiro cruzamento Estrutura × Monitoramentos
- USI03 consome o último resultado da Usinagem Interna.
- CRT03 consome o último resultado do Corte a Laser.
- A Estrutura não cria uma segunda análise; usa a fonte oficial dos monitoramentos.
- Exibe processo, encontrado/não encontrado, status e pendência.
- O índice é atualizado quando Usinagem ou Corte executam nova análise.


## V0.7.1.1 — Limpeza e controle de duplicidade da Estrutura
- Novo painel `Estruturas registradas`.
- Permite excluir uma estrutura específica.
- Permite limpar todos os registros da Estrutura do Produto.
- A limpeza não remove resultados dos monitoramentos de Usinagem ou Corte a Laser.
- Reanalisar o mesmo arquivo/conteúdo atualiza o registro anterior em vez de criar duplicatas.
- Operações de exclusão e limpeza são registradas na auditoria.


## V0.7.1.2 — Correção de migração do banco
- Corrigido `sqlite3.OperationalError: no such column: source_hash`.
- A inicialização agora verifica a estrutura real da tabela `product_structures` via `PRAGMA table_info`.
- Se o banco persistente veio de uma versão anterior, a coluna `source_hash` é criada automaticamente.
- A correção preserva usuários, histórico, evidências, monitoramentos e estruturas já existentes.


## V0.7.1.3 — Persistência completa dos monitoramentos
- O último resultado completo da Usinagem Interna passa a ser persistido no banco.
- O último resultado completo do Corte a Laser passa a ser persistido no banco.
- Atualizar ou analisar uma Estrutura do Produto não apaga mais visualmente as tabelas dos monitoramentos.
- Ao abrir/recarregar o dashboard, as tabelas de Usinagem e Corte são reconstruídas automaticamente a partir do último snapshot salvo.
- A restauração não executa uma nova análise; apenas recupera o último resultado oficial.
- Indicadores, cruzamento, histórico e evidências continuam usando a mesma fonte persistente.


## V0.7.1.4 — Persistência reforçada do Corte e feedback do cruzamento
- Reforçada a persistência do último resultado completo do Corte a Laser.
- Adicionado snapshot de segurança enviado pelo navegador após cada análise de Usinagem ou Corte.
- Atualizar/analisar uma Estrutura do Produto não deve mais fazer o Corte perder visualmente a análise anterior.
- O botão Atualizar cruzamento exibe "Atualizando..." durante o processo.
- Adicionadas notificações visuais de sucesso/erro e horário da atualização.


## V0.7.1.5 — Persistência robusta do Corte a Laser
- O último snapshot de Usinagem e Corte agora também é carregado diretamente pelo backend no HTML do dashboard.
- O Corte a Laser não depende apenas de uma requisição assíncrona para reconstruir sua tabela.
- Adicionado fallback local no navegador (`localStorage`) para preservar a última tabela caso a resposta do servidor falhe momentaneamente.
- O snapshot do servidor continua sendo a fonte principal; o armazenamento local funciona apenas como contingência visual.
- A restauração nunca substitui uma tabela válida por um resultado vazio.


## V0.7.1.6 — Persistência do Corte renderizada pelo backend
- O último resultado do Corte a Laser agora é renderizado diretamente pelo backend no HTML do dashboard.
- A tabela não depende mais do JavaScript para reaparecer após analisar/atualizar uma Estrutura do Produto.
- `window.laserResults` é inicializado diretamente com o snapshot persistido, preservando busca, filtros e detalhes.
- Uma restauração assíncrona vazia não pode sobrescrever a tabela já carregada.
- Adicionado endpoint de diagnóstico `/api/snapshot-status` para confirmar se os snapshots de Usinagem e Corte existem e quantas linhas possuem.

## V0.7.1.7 — Consulta detalhada das pendências do cruzamento
- Botão Ver detalhes por código.
- Exibe todos os requisitos, pendências e ações de adequação.
- Mostra pasta, caminho, status e última análise.
- Botão Abrir no monitoramento leva ao processo com o código filtrado.


## V0.7.2.0 — Validação consolidada da Estrutura do Produto
- Consolidação do cruzamento por estrutura/produto.
- Indicadores por estrutura: total de códigos, conformes, incompletos, não encontrados, externos e PRE.
- Status geral da estrutura: CONFORME, PENDÊNCIAS, CÓDIGOS NÃO ENCONTRADOS ou SEM AVALIAÇÃO.
- O sistema identifica quando existe monitoramento mais recente que o último cruzamento registrado.
- Novo estado `Cruzamento desatualizado`.
- `Atualizar cruzamento` passa a registrar um snapshot histórico do estado da estrutura.
- O histórico preserva contagens, status geral e dados completos do cruzamento.
- As regras provisórias USI03 / CRT03 / USI01 / CRT01 / PRE foram mantidas sem alteração nesta versão.


## V0.7.3.0 — Correções assistidas para piloto
- Base V0.7.2.0 preservada.
- Sugere correção determinística de nome de pasta e nome do datasheet.
- Renomeia somente após aprovação explícita.
- Bloqueia conflito de destino, caminho externo e item inexistente.
- Registra toda execução na auditoria e reanalisa o processo.
- Investiga automaticamente códigos CNC duplicados em toda análise de Usinagem.
- Duplicidade CNC é apenas sinalizada; nunca recebe correção automática.
- Sem IA nesta versão.


## V0.7.3.1 — Proteção de correções no Corte a Laser
- Mantém a V0.7.3.0 como base.
- "Aprovar e corrigir" só aparece quando um código CRT concreto (CRT + 6 dígitos) é identificado inequivocamente.
- CRT###### é apenas máscara de referência e nunca pode ser usado como nome de destino.
- Pastas PRE, USI ou sem CRT válido recebem somente orientação de atualização manual; o sistema não inventa nem converte códigos.
- Exemplo permitido: "CRT030042 - descrição" → "CRT030042".
- Exemplo bloqueado: "PRE030055 - descrição" → não sugerir "CRT######".


## V0.7.4.1 — Proteção de correções também na Usinagem
- Aplica à Usinagem a mesma regra conservadora validada no Corte a Laser.
- Pasta de Usinagem só recebe `Aprovar e corrigir` quando existe exatamente um código concreto USI###### ou PRE######.
- Se não houver código válido, houver múltiplos códigos ou o destino for ambíguo, o sistema apenas informa a inconformidade e exige correção manual.
- O datasheet só recebe sugestão automática quando o código CNC concreto no padrão CNC-RT-000 foi identificado.
- Máscaras, placeholders e códigos inferidos nunca são usados como nome de destino.
- Mantida a investigação de duplicidade CNC sem correção automática.


## V0.7.4.1 — Correção de configuração da Biblioteca CAD
- Corrige os botões Configurar / alterar da Biblioteca CAD na Visão Geral e na página da Biblioteca.
- A abertura do painel não depende mais de onclick inline; usa delegação de eventos no JavaScript principal.
- Mantém o mesmo POST /process-environment e a persistência já existente.
- Fecha o painel por Cancelar, X, clique no fundo ou tecla Esc.


## V0.7.4.2 — Abrir pasta nos detalhes da Biblioteca CAD
- Mantém integralmente a lógica validada da V0.7.4.1.
- Adiciona o botão `📂 Abrir pasta` ao painel lateral de detalhes/conformidade da Biblioteca CAD.
- A abertura reutiliza o endpoint seguro `/api/open-folder`.
- Ajusta também a identificação textual dos scripts de instalação/execução para V0.7.4.2.


## V0.7.4.3 — Abrir pasta nos painéis de conformidade
- Mantém a Biblioteca CAD da V0.7.4.2.
- Adiciona `📂 Abrir pasta` ao painel de detalhes da Usinagem.
- Adiciona `📂 Abrir pasta` ao painel de detalhes do Corte a Laser.
- Biblioteca CAD já possui o mesmo recurso.
