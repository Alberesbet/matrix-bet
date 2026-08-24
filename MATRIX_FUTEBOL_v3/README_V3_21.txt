MATRIX FUTEBOL V3.21

CORREÇÕES PRINCIPAIS

1) NOTEBOOK + CELULAR
- Motor AUTO DEMO roda no servidor.
- O navegador não cria nem finaliza mais entradas sozinho.
- Histórico canônico do servidor.
- Service Worker apaga caches antigos.
- Página principal enviada com no-store.
- Depois do deploy, confirme V3.21 no topo nos dois aparelhos.

Para recuperar o histórico maior:
1. Abra primeiro o NOTEBOOK.
2. Espere SINCRONIZAÇÃO = SERVIDOR OK.
3. Atualize o CELULAR.
4. Os dois devem convergir para a mesma lista.

2) CONTADORES
Mostra separadamente:
- Apostas totais
- Auto DEMO realizadas
- Em andamento
- Finalizadas
- Vitórias
- Derrotas
- Canceladas

AO VIVO = partidas.
EM ANDAMENTO = apostas.
Se houver mais de uma aposta na mesma partida, os números podem ser diferentes.

3) VALORES
- Valor efetivamente apostado: EXCLUI canceladas.
- Valor em andamento.
- Valor cancelado/devolvido.
- Movimentação registrada: inclui tudo que foi lançado.
- Lucro/prejuízo realizado.

4) FINALIZAÇÃO
Prioridade:
1. Betfair API: market CLOSED + runner WINNER.
2. BF Bot CSV: Vencedor(es).
3. SportMonks: placar final quando existe Fixture ID.

5) BETFAIR API
Quando BETFAIR_APP_KEY e BETFAIR_SESSION_TOKEN estiverem no Render:
- catálogo de futebol automático;
- sem filtro por país;
- InPlay confirmado;
- finalização automática;
- volume por seleção/time;
- mercados brasileiros também entram quando disponíveis na Exchange.

6) BRASIL
Nova aba BRASIL.
Prioriza nacionais, estaduais e regionais, incluindo:
Brasileirão, Copa do Brasil, Pernambucano, Copa do Nordeste,
Paulista, Carioca, Mineiro, Gaúcho, Cearense, etc.

7) TOTAL CORRESPONDIDO
É do MERCADO daquela partida, não de todos os jogos da Betfair.

8) MODO
Continua DEMONSTRAÇÃO. Nenhuma ordem real é enviada.
