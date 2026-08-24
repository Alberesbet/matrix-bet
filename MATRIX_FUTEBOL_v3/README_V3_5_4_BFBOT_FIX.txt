MATRIX FUTEBOL V3.5.4 - CORREÇÃO DEFINITIVA DO FEED BFBOT

PROBLEMA CORRIGIDO
A versão anterior retirava a tip quando faltavam menos de 60 minutos para o jogo.
O Bf Bot Manager usa SportMonksFixtureId para encontrar os IDs Betfair quando
os dados ficam disponíveis perto de 30 minutos antes do início. Assim, a tip
sumia antes do momento em que o BF Bot poderia vinculá-la.

CORREÇÃO
- Tips permanecem no CSV até o início do jogo.
- BFBOT_MIN_MINUTES_BEFORE_START padrão agora é 0.
- SportMonksFixtureId continua ativo.
- SelectionName continua HOME/AWAY/The Draw.
- MarketType=MATCH_ODDS.
- BetType=BACK.
- BSP=false (PIB desligado).
- StartTime removido do CSV porque é opcional para este fluxo.

CSV:
Provider,SportMonksFixtureId,SelectionName,MarketType,BetType,Size,BSP,EventName

NO BF BOT MANAGER
- Deixe os mercados MATCH_ODDS carregados.
- Recarregue o feed MATRIX a cada 15 minutos.
- IDs podem permanecer 0 até aproximadamente 30 minutos antes do início.
- Teste em modo simulação antes de ativar qualquer estratégia em modo real.
