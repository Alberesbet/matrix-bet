MATRIX BET V5.9.6 - DOIS APPS INDEPENDENTES

OBJETIVO
Ter dois PWAs realmente separados no mesmo celular:
1) MATRIX BET (usuário)
2) MATRIX BET ADMIN (administrador)

POR QUE
Dois PWAs na mesma origem/domínio podem compartilhar armazenamento e ter conflitos
de instalação/escopo. Esta versão foi preparada para rodar em DOIS Web Services do Render.

SERVIÇO 1 - USUÁRIO (já existente)
Nome sugerido: matrix-bet
URL atual: https://matrix-bet.onrender.com
Environment:
APP_MODE=user
DATABASE_URL=<mesmo PostgreSQL>

SERVIÇO 2 - ADMIN (criar no Render)
Nome sugerido: matrix-bet-admin
URL esperada: https://matrix-bet-admin.onrender.com
Use o MESMO repositório GitHub e a mesma Root Directory/Runtime do serviço atual.
Environment:
APP_MODE=admin
DATABASE_URL=<EXATAMENTE o mesmo PostgreSQL do serviço usuário>

Também copie para o serviço ADMIN as variáveis necessárias do projeto
(ADMIN_EMAIL/ADMIN_PASSWORD se ainda usadas, SMTP se necessário etc.).

RESULTADO
- Abrir matrix-bet.onrender.com instala MATRIX BET.
- Abrir matrix-bet-admin.onrender.com instala MATRIX BET ADMIN.
- Cada um tem origem diferente e armazenamento local separado.
- Você pode permanecer logado nos dois simultaneamente.
- Os dois enxergam os mesmos usuários/apostas porque usam o mesmo PostgreSQL.

DIAGNÓSTICO
/api/app-mode
retorna mode=user ou mode=admin e a versão 5.9.6.
