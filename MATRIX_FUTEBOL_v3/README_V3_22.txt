MATRIX FUTEBOL V3.22
AO VIVO + FINALIZAÇÃO CORRIGIDOS

ERRO ENCONTRADO
Na V3.21, MATRIX_DEMO_FINISH_GRACE_MINUTES estava com padrão de 180 minutos.
Uma partida iniciada às 12:00 podia ficar "em andamento" até perto das 15:00.
V3.22 reduz a janela para 130 minutos.

AO VIVO
- Se Betfair API estiver conectada: usa somente inplay=true da Betfair.
- Se Betfair API NÃO estiver conectada: usa SportMonks /livescores/inplay.
- O CSV antigo do BF Bot não é mais considerado "ao vivo" apenas porque dizia OPEN.
- "PROVÁVEL AO VIVO" não entra no contador principal.

FINALIZAÇÃO
A cada ciclo do servidor:
1. consulta Betfair API (se conectada);
2. procura vencedor no CSV do BF Bot;
3. consulta SportMonks;
4. se a aposta antiga não tem Fixture ID, tenta localizar a partida pelos nomes dos dois times + horário;
5. se encontrar placar final, marca GANHOU ou PERDEU;
6. se o jogo já ultrapassou 130 min e ainda não há resultado confirmado:
   tira de EM ANDAMENTO e marca AGUARDANDO CONFIRMAÇÃO FINAL.

CONTADORES
- AO VIVO: partidas atualmente ao vivo na fonte atual.
- Partidas em andamento: partidas com aposta ainda realmente em andamento.
- Entradas pendentes: todas as apostas ainda sem liquidação.
- Aguardando resultado: partida já saiu do andamento, mas resultado ainda precisa ser confirmado.
- Finalizadas: GANHOU + PERDEU.

IMPORTANTE
Nunca inventa vitória ou derrota apenas pelo horário.
Se a Betfair API não estiver conectada, SportMonks é o fallback automático.

BOTÃO ANALISAR AGORA
Força nova análise + reconciliação/finalização imediata.

MODO
Continua DEMONSTRAÇÃO.
Nenhuma ordem real é enviada.
