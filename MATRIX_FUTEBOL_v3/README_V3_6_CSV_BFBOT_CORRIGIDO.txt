MATRIX FUTEBOL V3.6 - CSV BFBOT CORRIGIDO

ALTERAÇÃO FEITA DIRETAMENTE NA BASE DOC-20260824-WA0012.zip.

FEED PRINCIPAL:
/bfbot/tips.csv

Agora gera:
Provider,Handicap,SportMonksFixtureId,SelectionName,MarketName,EventName,
MarketType,StartTime,BetType,Size,Points,Price,MinPrice,MaxPrice,BSP

Mudanças:
- SelectionName = nome REAL do time escolhido (ex.: Viborg FF), não HOME/AWAY.
- EventName = 'Casa v Fora', padrão Betfair.
- MarketName = Match Odds.
- MarketType = MATCH_ODDS.
- StartTime = UTC no formato YYYY-MM-DD HH:MM:SS.
- SportMonksFixtureId continua junto como fallback.
- BetType = BACK.
- BSP = False (PIB desligado).
- Price = 0 (usa preço da estratégia/mercado).
- MinPrice = 1.01 / MaxPrice = 1000.

FEED FALLBACK:
/bfbot/tips_sportmonks.csv
Usa HOME/AWAY/DRAW + SportMonksFixtureId, conforme o formato SportMonks do BFBot.

IMPORTANTE NO BF BOT:
Apague as tips MATRIX antigas antes de recarregar /bfbot/tips.csv.
Teste em SIMULAÇÃO antes de qualquer modo real.
