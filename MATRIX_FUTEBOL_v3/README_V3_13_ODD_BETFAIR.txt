MATRIX FUTEBOL V3.13 - ODD BETFAIR REAL

REGRA:
- MATRIX = análise (H2H, estatísticas, filtro).
- BETFAIR = odd usada para simulação/execução.

A V3.13 NÃO usa mais x.odd da análise para calcular retorno financeiro.

Ela só libera:
Retorno = stake x odd BETFAIR
Lucro = retorno - stake

Se a odd Betfair:
- não existir;
- estiver desatualizada;
- ou pertencer a outra seleção,

a simulação e o feed de execução ficam bloqueados.

Na tela:
- "Odd mediana (análise)" não é cotação executável.
- "Melhor odd recebida (análise)" não é cotação executável.
- "Odd BETFAIR para execução" é a cotação que vale para retorno/aposta.
- O histórico grava "Fonte da odd = BETFAIR".

Observação:
O CSV "Exportar todos os dados visíveis" recebido mostra diretamente a odd
do 1º favorito. Por segurança, a versão só aceita essa odd quando o time
escolhido pela MATRIX é o mesmo 1º favorito da Betfair.
