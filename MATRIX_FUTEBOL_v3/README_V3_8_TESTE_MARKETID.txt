MATRIX FUTEBOL V3.8 - TESTE MARKET ID DIRETO

NOVO ENDPOINT DE DIAGNÓSTICO:
  /bfbot/test_marketid.csv

Conteúdo:
Provider,MarketId,SelectionName,EventName,MarketType,BetType,Size,BSP
MATRIX_TESTE_NAO_APOSTAR,1.261459879,Sabah FA,Sabah FA v Imigresen FC,MATCH_ODDS,BACK,0.01,False

OBJETIVO:
Confirmar se o BF Bot Manager preenche diretamente o Market ID 1.261459879
quando a tip é importada com MarketId explícito.

IMPORTANTE:
- O feed principal /bfbot/tips.csv NÃO foi alterado por este teste.
- NÃO iniciar nenhuma estratégia durante o teste.
- Provider do teste é MATRIX_TESTE_NAO_APOSTAR para não misturar com as tips normais.
- Depois de importar, abra Gerenciar Dicas e confira se MarketId deixa de ser 0.
