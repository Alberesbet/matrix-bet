MATRIX FUTEBOL V3.14 - AUTO DEMO + VALOR NA SELEÇÃO

MODO
- Demonstração/simulação somente.
- Não envia dinheiro real.

CONFIGURAÇÃO PADRÃO
- Banca demo: R$ 1.000,00
- Valor por entrada: R$ 10,00
- Máximo: 2 entradas por partida
- Janela de entrada: minuto 2 até 75
- Odd: 1,30 até 3,50
- Total correspondido mínimo do mercado: R$ 500,00
- Valor mínimo visível junto ao nome/seleção: R$ 50,00
- Máximo de 20 apostas demo pendentes

ANÁLISE POR VALOR NO NOME
Exemplo do BF Bot Manager:
Sabah FA, R$515,77@2,32

A V3.14 lê:
- Seleção: Sabah FA
- Valor visível na seleção: R$515,77
- Odd Betfair: 2,32

Esse valor entra no índice de triagem do AUTO DEMO.
IMPORTANTE: esse R$515,77 é tratado como liquidez/valor disponível na cotação
exibida. Não é interpretado como percentual de pessoas apostando no time.

MERCADOS DO AUTO DEMO
- Resultado da partida (Match Odds)
- Mais/Menos de 2,5 gols
- Ambas marcam, quando esse mercado estiver disponível no CSV

HISTÓRICO
- Aba MINHAS APOSTAS mostra resumo mensal:
  apostas, vitórias, derrotas, pendentes, valor apostado e lucro/prejuízo.
- Quando um CSV posterior trouxer Vencedor(es), o sistema pode fechar
  a aposta demo como GANHOU ou PERDEU.

TESTE FEITO COM O CSV REAL ENVIADO
No arquivo betfair_visiveis.csv usado para validação:
- 745 linhas lidas
- 9 jogos/mercados ao vivo identificados no horário do teste
- 8 entradas AUTO DEMO passaram pelos filtros, considerando também
  o valor disponível junto ao nome/seleção.

Para renovar odds e valores, exporte novamente "todos os dados visíveis"
no BF Bot Manager e importe no MATRIX.
