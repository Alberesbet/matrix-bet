MATRIX FUTEBOL V3.7 - BETFAIR MIRROR

OBJETIVO
Mostrar no MATRIX os mercados que estão carregados no BF Bot Manager, inclusive
jogos que não aparecem no feed SportMonks atual.

COMO FUNCIONA
1. BF Bot Manager -> EVENTOS E MERCADOS -> Export markets
   (ou Export all visible data para trazer colunas adicionais como Status).
2. MATRIX -> aba BETFAIR -> IMPORTAR MERCADOS BFBOT.
3. O MATRIX mostra EventName, EventId, MarketName, MarketId, StartTime,
   TotalMatched e Status quando essas colunas existirem.
4. O MATRIX tenta ligar cada evento importado aos jogos SportMonks pelo nome
   casa/fora. Quando encontra, mostra placar/tempo/sinal/odd do MATRIX.

IMPORTANTE
- BF Bot Manager V3 possui botão manual Export markets; não há uma auto-exportação
  pública documentada. Portanto o Render não consegue enxergar sozinho a grade
  do programa Windows em tempo real.
- O último CSV importado é guardado também no navegador e restaurado automaticamente.
- O BF Bot Manager continua sendo quem monitora preços e executa a estratégia.
- Teste sempre em simulação antes de modo real.

TRANSMISSÃO
- Botão BETFAIR TV OFICIAL abre https://livevideo.betfair.bet.br/
- Botão EXCHANGE AO VIVO abre a lista oficial de eventos ao vivo.
- O vídeo não é copiado nem retransmitido dentro do MATRIX; disponibilidade
  depende da Betfair e dos direitos do evento.
