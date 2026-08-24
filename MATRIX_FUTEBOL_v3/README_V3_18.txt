MATRIX FUTEBOL V3.18 - PWA + OVER/UNDER 1.5 + VOLUME POR TIME

1. CORREÇÃO DO "TOTAL CORRESPONDIDO"
O campo do CSV "Total correspondido" pertence ao MERCADO específico daquela partida.

Exemplo:
Verl x Hamburgo -> Resultado da partida -> R$31.212,90

Esse valor NÃO soma todos os jogos da Betfair.
Ele corresponde somente ao mercado Resultado da partida de Verl x Hamburgo,
somando as seleções desse mercado (Verl / Empate / Hamburgo).

2. VOLUME CORRESPONDIDO POR TIME/SELEÇÃO
O CSV do BF Bot Manager não fornece o total correspondido separado por seleção.
A V3.18 ficou pronta para buscar isso pela API oficial da Betfair.

Configurações de servidor:
BETFAIR_APP_KEY
BETFAIR_SESSION_TOKEN

Quando configuradas, a tela mostra:
- Verl: total correspondido
- Empate: total correspondido
- Hamburgo: total correspondido
- qual seleção tem maior volume
- se a seleção escolhida pelo robô é a de maior volume

As credenciais ficam SOMENTE no servidor/Render, nunca no navegador.

3. NOVO MERCADO
AUTO DEMO agora reconhece também:
- Resultado da partida
- Mais/Menos de 1,5 gols
- Mais/Menos de 2,5 gols
- Ambas marcam (quando disponível)

Máximo padrão DEMO por partida: 3 entradas.

4. INSTALAR APP / CONTINUAR WEB
A V3.18 é PWA instalável:
- botão INSTALAR APP no topo;
- escolha INSTALAR APP ou CONTINUAR PELA WEB;
- manifest com ícones 192 e 512;
- service worker atualizado.

5. MODO REAL
Permanece BLOQUEADO nesta versão.
Recomendação: validar a DEMO durante o período planejado antes de ativar execução real.
A estrutura de volume por seleção foi preparada porque esse dado deve ser validado
antes de usar como confirmação em dinheiro real.
