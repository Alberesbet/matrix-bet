MATRIX FUTEBOL V3.12 - AO VIVO ATUALIZADO

ALTERAÇÕES
- Atualização visual/API a cada 5 segundos.
- Jogos "provável ao vivo" entram automaticamente quando o horário de início passa.
- Jogos antigos de Match Odds saem automaticamente depois de 115 minutos
  (configurável por BETFAIR_LIVE_MAX_MINUTES).
- O MATRIX mostra a idade dos dados/odds importados do BF Bot Manager.
- Dados visíveis com mais de 120 segundos são marcados como desatualizados.
- Odds antigas aparecem como "Última odd importada", não como odd atual.
- Botão "ATUALIZAR DADOS AO VIVO" abre diretamente a importação do CSV
  "Exportar todos os dados visíveis".

IMPORTANTE
O tempo/lista pode ser recalculado automaticamente a partir do horário.
Odds, volumes e status exatos da Betfair só mudam quando o arquivo
"betfair_visiveis.csv" é exportado novamente pelo BF Bot Manager e importado.
Isso evita o robô tratar uma odd velha como se fosse cotação atual.

Durante os testes, mantenha execução em SIMULAÇÃO.
