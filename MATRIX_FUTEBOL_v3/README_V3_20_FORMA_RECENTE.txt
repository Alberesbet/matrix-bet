MATRIX FUTEBOL V3.20 - FORMA RECENTE DOS ÚLTIMOS 2 JOGOS

NOVO
Para cada dupla, o MATRIX consulta os últimos 2 jogos anteriores de CADA time.

Mostra:
- adversário
- data
- CASA ou FORA
- VITÓRIA / EMPATE / DERROTA
- placar
- pontos
- gols pró / contra
- força recente
- vantagem de momento entre os dois times

PONTUAÇÃO TRANSPARENTE
Vitória = 3
Empate  = 1
Derrota = 0

Classificação:
- MUITO FORTE
- FORTE
- REGULAR
- FRACA
- MUITO FRACA

USO NA ANÁLISE
A forma recente entra como confirmação adicional:
- peso máximo: 20%
- H2H: até 20%
- mercado/odds continua sendo o principal peso

Com apenas dois jogos, a forma recente NÃO domina a decisão.

SPORTMONKS
Usa o endpoint de fixtures por intervalo e time:
GET /fixtures/between/{start_date}/{end_date}/{team_id}
com includes participants;scores;state;league.

AUTO DEMO
Quando o jogo Betfair está linkado ao SportMonks, cada entrada AUTO DEMO também
registra:
- forma recente de ambos os times
- momento do time escolhido
- qual time chega com melhor momento
- se a forma recente confirma ou não a entrada

HISTÓRICO
As novas apostas guardam esse retrato da forma recente no momento da entrada.
Apostas antigas não recebem retroativamente esses campos.

MODO
Continua somente DEMONSTRAÇÃO. Nenhuma ordem real é enviada.
