MATRIX FUTEBOL V3.19 - SYNC NOTEBOOK + CELULAR

PROBLEMA CORRIGIDO
Até a V3.18 as apostas DEMO ficavam em localStorage.
localStorage pertence a cada navegador/aparelho, por isso era possível ter:
- notebook: 19 Minhas Apostas / 17 Auto DEMO
- celular: 11 Minhas Apostas / 11 Auto DEMO

V3.19
O histórico DEMO passa a ser sincronizado pelo servidor MATRIX.

Fluxo:
1. Cada aparelho envia o histórico local para /api/demo-bets/sync.
2. O servidor une as listas por demo_key/MarketId/seleção.
3. O servidor devolve a lista canônica.
4. Notebook e celular substituem o cache local pela mesma lista.
5. O processo ocorre automaticamente a cada atualização do painel.

SINCRONIZA
- Minhas apostas
- Auto DEMO feitas
- Saldo DEMO
- Status GANHOU/PERDEU/PENDENTE
- Cancelamentos
- Dados e motivos de cada entrada

PRIMEIRO USO APÓS DEPLOY
Para preservar o histórico maior:
1. Abra primeiro no NOTEBOOK (onde estão 19/17).
2. Aguarde aparecer SINCRONIZADO.
3. Abra/atualize o celular.
4. Em poucos segundos os contadores devem ficar iguais.

SEGURANÇA CONTRA PERDA
O servidor mantém cache em arquivo /tmp e memória.
Além disso, cada navegador mantém sua cópia local e reenvia ao servidor,
de modo que os aparelhos podem reidratar o histórico após reinício do serviço.

IMPORTANTE
Isto sincroniza somente a DEMONSTRAÇÃO do MATRIX.
Não envia nem sincroniza apostas reais Betfair.
