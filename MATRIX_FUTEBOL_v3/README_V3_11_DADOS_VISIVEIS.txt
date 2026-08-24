MATRIX FUTEBOL V3.11

Ajustado com o arquivo REAL betfair_visiveis.csv do BF Bot Manager.

FORMATO CONFIRMADO DO ARQUIVO:
- 745 linhas no arquivo analisado
- 206 linhas "Resultado da partida"
- Status = OPEN
- Hora de início
- Evento/mercado = Time A x Time B\Mercado
- 1º favorito = seleção + valor disponível + odd
- Total correspondido
- IP, Tempo e Placar ao vivo estavam vazios

USO:
1. BETFAIR -> 1. IMPORTAR MERCADOS / IDs
   Selecione o CSV criado em "Exportar mercados".
2. BETFAIR -> 2. IMPORTAR DADOS VISÍVEIS
   Selecione o CSV criado em "Exportar todos os dados visíveis".

O MATRIX cruza os dois:
- arquivo 1: MarketId/EventId
- arquivo 2: status/horário/favorito/odd/liquidez

AO VIVO:
- IP preenchido -> AO VIVO CONFIRMADO
- IP vazio + Status OPEN/SUSPENDED + início já passou -> PROVÁVEL AO VIVO • BETFAIR
- SportMonks não é mais obrigatória para aparecer nessa aba.

O feed de execução continua exigindo MarketId real.
Mantenha a estratégia em simulação durante os testes.
