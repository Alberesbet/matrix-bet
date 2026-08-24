MATRIX FUTEBOL V3.25 - FINALIZAÇÃO SPORTMONKS FORTE

OBJETIVO
Finalizar as apostas DEMO mesmo quando a aba RESULTADOS do BF Bot está vazia.

NOVO FLUXO
BF Bot:
- fornece jogos/mercados/odds/horários.

SportMonks:
- procura a partida pelo nome dos DOIS times + data + horário;
- obtém Fixture ID;
- consulta diretamente /fixtures/{id};
- lê estado final e placar;
- o MATRIX calcula GANHOU/PERDEU.

MERCADOS LIQUIDADOS PELO PLACAR
- Resultado da partida (1X2)
- Mais/Menos 1,5 gols
- Mais/Menos 2,5 gols
- Ambas Marcam

SEGURANÇA DE DADOS
- Não inventa resultado pelo horário.
- Se não houver casamento seguro dos dois times, continua aguardando.
- Se houver placar mas mercado desconhecido, não marca vitória/derrota.

BOTÃO NOVO
RECONCILIAR RESULTADOS
Força nova busca no SportMonks e tenta liquidar as pendentes imediatamente.

MODO
DEMONSTRAÇÃO. Não envia aposta real.
