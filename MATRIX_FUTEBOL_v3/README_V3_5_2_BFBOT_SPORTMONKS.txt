MATRIX FUTEBOL V3.5.2

CORREÇÃO BFBOT:
- CSV agora envia SportMonksFixtureId.
- Para MATCH_ODDS:
  HOME -> SelectionName=HOME
  AWAY -> SelectionName=AWAY
  DRAW -> SelectionName=The Draw
- CSV envia BSP=false, portanto PIB/BSP fica desligado.
- Também envia EventName e StartTime.
- O Bf Bot Manager pode localizar os IDs Betfair automaticamente usando o
  SportMonksFixtureId quando os dados de correspondência estiverem disponíveis.

NOVO CABEÇALHO CSV:
Provider,SportMonksFixtureId,SelectionName,MarketType,BetType,Size,BSP,EventName,StartTime

IMPORTANTE:
- No Gerenciar Dicas, IDs podem continuar 0 até perto do início do jogo.
- O manual atual do Bf Bot Manager informa que, com SportMonksFixtureId,
  ele encontra os IDs Betfair quando os dados de live score ficam disponíveis,
  tipicamente a partir de cerca de 30 minutos antes do início.
- PIB/BSP deve permanecer DESMARCADO.
- Teste primeiro em simulação.
