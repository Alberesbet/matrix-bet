MATRIX FUTEBOL V3.17 - ANÁLISE DE ENTRADA CLARA

AUTO DEMO VERMELHO
Na versão anterior, o selo AUTO DEMO da aba AUTO DEMO usava a classe visual
"live", que é rosa/vermelha. Isso NÃO indicava erro, perda ou rejeição.
Na V3.17 o selo AUTO DEMO foi padronizado para VERDE.

CADA ENTRADA MOSTRA
- TIME/SELEÇÃO ESCOLHIDA PELO ROBÔ
- 1º favorito Betfair/BF Bot
- confirmação do favorito
- odd Betfair
- probabilidade implícita da odd
- valor disponível NESTA seleção/cotação
- total correspondido em TODO o mercado
- índice de triagem MATRIX
- POR QUE O ROBÔ ENTROU?

DIFERENÇA DOS VALORES
VALOR DISPONÍVEL NA SELEÇÃO:
dinheiro disponível naquela cotação exibida para o time/seleção.

TOTAL CORRESPONDIDO DO MERCADO:
todo o dinheiro já negociado no mercado, incluindo outras seleções e BACK/LAY.

O total correspondido NÃO é o total apostado somente no time escolhido.

TIME MAIS APOSTADO
O CSV atual não fornece o total correspondido separado por cada time.
Por isso a V3.17 não inventa percentuais como 70/30. Ela mostra exatamente
o que o arquivo fornece: 1º favorito, odd e valor disponível na seleção.

As novas apostas AUTO DEMO guardam esses detalhes no histórico.
Apostas antigas podem não ter todos os novos campos porque foram registradas
antes desta versão.
