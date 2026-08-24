MATRIX FUTEBOL V3.9 - MARKETID OBRIGATÓRIO

RESULTADO DO TESTE
O MarketId 1.261459879 foi importado corretamente pelo BF Bot Manager.
A V3.9 aplica esse mesmo princípio no feed principal.

COMO FUNCIONA
1. Exporte os mercados carregados no BF Bot Manager ("Export markets").
2. No MATRIX, abra BETFAIR -> IMPORTAR MERCADOS BFBOT e selecione esse CSV.
3. O MATRIX guarda os mercados e seus MarketIds.
4. Para cada sinal aprovado, o MATRIX procura o mesmo evento Match Odds.
5. Se encontrar MarketId:
     envia MarketId + SelectionName + BACK + stake.
6. Se NÃO encontrar MarketId:
     o sinal fica BLOQUEADO e não entra no /bfbot/tips.csv.

OBJETIVO
Nunca mais mandar novas tips de execução com Market ID = 0.

FEED PRINCIPAL
/bfbot/tips.csv

COLUNAS
Provider,MarketId,EventId,SelectionName,EventName,MarketType,BetType,Size,BSP

DIAGNÓSTICO
/api/bfbot/unmatched
mostra os sinais aprovados que ainda aguardam MarketId.

IMPORTANTE
O BF Bot Manager não disponibiliza auto-exportação pública documentada dos
mercados. Portanto, para atualizar a lista completa de MarketIds, o CSV
"Export markets" ainda precisa ser fornecido ao MATRIX quando a grade mudar.

Teste a estratégia primeiro em simulação antes de usar modo real.
