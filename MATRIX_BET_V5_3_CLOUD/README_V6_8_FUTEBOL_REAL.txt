MATRIX BET V6.8 - FUTEBOL REAL SPORTMONKS

CORREÇÃO PRINCIPAL
- A página FUTEBOL não usa mais a lista fixa/demo de /api/events.
- Ela usa diretamente /api/real/fixtures, já autenticado pelo próprio app.
- As ligas são montadas dinamicamente a partir da resposta da Sportmonks.
- Jogos com has_odds=true mostram VER ODDS REAIS.
- O botão abre /api/real/fixtures/{id}/odds.
- Busca de jogos/equipes/ligas funciona na lista real.
- Se a Sportmonks não retornar jogos ou o plano não liberar odds, a tela mostra isso claramente.

IMPORTANTE
- O cupom/aposta existente continua DEMO.
- Esta correção exibe dados e odds reais; não converte a plataforma em operadora de apostas reais.
- SPORTMONKS_TOKEN deve permanecer configurado no Render.
