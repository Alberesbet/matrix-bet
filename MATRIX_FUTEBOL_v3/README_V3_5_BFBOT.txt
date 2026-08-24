MATRIX - FUTEBOL V3.5 - BFBOT MANAGER

NOVO:
- Endpoint público de tips no formato CSV:
  /bfbot/tips.csv
- Endpoint de diagnóstico:
  /api/bfbot
- Aba BFBOT no painel.
- Exporta somente sinais pré-jogo APROVADOS.
- Formato:
  Provider,SelectionName,MarketType,BetType,Size,EventName
- MarketType = MATCH_ODDS
- BetType = BACK
- Size = stake do MATRIX
- Empate é exportado como "The Draw".
- Não exporta ao vivo pelo feed web porque a importação por URL do Bf Bot Manager
  trabalha em ciclos agendados e não é adequada a execução segundo a segundo.

CONFIGURAÇÕES OPCIONAIS NO RENDER:
BFBOT_ENABLED=true
BFBOT_PROVIDER=MATRIX
BFBOT_MIN_MINUTES_BEFORE_START=60
BFBOT_MAX_TIPS=20

COMO USAR NO BFBOT MANAGER:
1. Deploy desta versão no Render.
2. No MATRIX > aba BFBOT, copie a URL exibida.
3. No Bf Bot Manager, configure importação automática de tips por web location/URL.
4. Use essa URL do MATRIX.
5. Configure Autoload para mercados de futebol MATCH_ODDS.
6. Configure a estratégia com "Bet on imported tips" / "Apostar em tips importadas".
7. TESTE PRIMEIRO NO MODO SIMULAÇÃO DO BFBOT MANAGER.

IMPORTANTE:
- O Bf Bot Manager, não o MATRIX, autentica na Betfair e envia a aposta.
- Não coloque senha da Betfair no GitHub ou no MATRIX.
- Sem MarketId da Betfair, o Bf Bot Manager precisa ter os mercados MATCH_ODDS
  carregados automaticamente para ligar as tips às seleções.
- Nomes dos times precisam coincidir com os nomes reconhecidos na Betfair.
