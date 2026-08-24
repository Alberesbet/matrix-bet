MATRIX BET V5.9.3 - CADASTRO ADMIN CORRIGIDO

Corrigido:
- geração de salt da senha do administrador;
- hash da senha com salt;
- preenchimento do campo salt;
- preenchimento de created_at;
- rollback em caso de erro no banco;
- versão visível V5.9.3.

Fluxo testado:
1. setup-status informa que não existe ADM;
2. cadastra primeiro administrador;
3. setup fica bloqueado;
4. login do ADM funciona;
5. painel administrativo autenticado abre.

ADMIN:
https://matrix-bet.onrender.com/static/admin.html
ou
https://matrix-bet.onrender.com/painel-adm
