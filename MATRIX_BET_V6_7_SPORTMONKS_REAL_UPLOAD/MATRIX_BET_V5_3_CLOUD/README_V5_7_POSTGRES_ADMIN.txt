MATRIX BET V5.7 - POSTGRESQL + ADMIN COMPLETO

- PostgreSQL via DATABASE_URL; SQLite apenas fallback/local.
- ADMIN: busca/filtro de usuários e apostas, detalhes do usuário, histórico de atividade,
  suporte, bloqueio/desbloqueio e ajuste de saldo DEMONSTRATIVO.
- PWA mantido.

No Render:
1. Criar Render Postgres.
2. Em matrix-bet > Environment, configurar DATABASE_URL com a Internal Database URL.
3. Manter ADMIN_EMAIL, ADMIN_PASSWORD e ADMIN_USERNAME.
4. Deploy.
5. Abrir /health e confirmar database=postgresql e persistent_database=true.

ATENÇÃO: trocar para PostgreSQL novo não copia automaticamente usuários do SQLite.
O Postgres gratuito do Render é para testes e expira após 30 dias; produção deve usar plano persistente com backups.
