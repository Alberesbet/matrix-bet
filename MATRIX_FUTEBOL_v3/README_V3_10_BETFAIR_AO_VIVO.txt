MATRIX FUTEBOL V3.10 - BETFAIR AO VIVO

CORREÇÕES
1. "Resultado da partida" agora é reconhecido como Match Odds.
2. A aba AO VIVO usa Betfair/BF Bot Manager + SportMonks.
3. Jogos Betfair que não existem na SportMonks podem aparecer no AO VIVO.
4. Se o CSV tiver InPlay/Status, o MATRIX usa isso.
5. Se o CSV não tiver InPlay/Status, o MATRIX usa o horário de início como inferência
   apenas numa janela curta após o kickoff e deixa isso marcado como inferido.
6. O feed de execução continua exigindo MarketId real.

MELHOR CSV PARA AO VIVO
No BF Bot Manager, use preferencialmente:
Importar/Exportar -> Exportar todos os dados visíveis

"Exportar mercados" continua útil para MarketId/EventId/StartTime, mas pode não
trazer Status/InPlay.

IMPORTANTE
A lista Betfair importada é um espelho do momento em que o CSV foi exportado.
Ela não se atualiza sozinha no Render sem nova exportação/importação.
