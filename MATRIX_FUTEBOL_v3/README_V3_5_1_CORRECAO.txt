MATRIX FUTEBOL V3.5.1

CORREÇÃO CRÍTICA:
- Corrigido deadlock em /api/status.
- O painel não deve mais ficar em "..." com todos os contadores em 0.
- BFBOT deixa de aparecer DESATIVADO apenas por falta de resposta da API.
- Cache atualizado para v351.

CAUSA:
A rota /api/status segurava LOCK e chamava bfbot_tips(), que tentava adquirir o mesmo LOCK.
Com threading.Lock normal isso travava a requisição indefinidamente.

CORREÇÃO:
- LOCK alterado para threading.RLock().
- /api/status agora copia STATE e libera o lock antes de calcular as tips BFBOT.
