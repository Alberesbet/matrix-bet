MATRIX FUTEBOL V3.24

CORRIGE A PONTE BF BOT V3.23.

Problemas identificados nas fotos:
- mercado_betfair.csv -> linhas=0
- betfair_visiveis.csv -> linhas=0
- test_marketid.csv -> erro 400 repetido
- PONTE BF BOT -> DESATUALIZADA mesmo com a janela aberta

Solução:
- Base64 dos bytes originais.
- Auto-detecção de encoding.
- Auto-detecção de separador.
- Parser de cabeçalhos flexível.
- Heartbeat.
- Arquivos de teste/tips ignorados.
- Diagnóstico de encoding/separador/cabeçalhos retornado pelo servidor.

IMPORTANTE:
Para resultados GANHOU/PERDEU, o BF Bot precisa fornecer/exportar o resultado
ou Vencedor(es), ou o SportMonks precisa conseguir casar a partida e obter
o placar final. O MATRIX não inventa resultado apenas pelo horário.
