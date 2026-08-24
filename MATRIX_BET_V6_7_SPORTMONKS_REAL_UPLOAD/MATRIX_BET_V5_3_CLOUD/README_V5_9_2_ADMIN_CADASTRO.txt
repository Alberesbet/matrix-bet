MATRIX BET V5.9.2 - CADASTRO INICIAL DO ADMINISTRADOR

ADMIN:
https://matrix-bet.onrender.com/static/admin.html
ou
https://matrix-bet.onrender.com/painel-adm

NOVO:
- se ainda não existir administrador, aparece "Primeiro cadastro do administrador";
- cadastro pede nome, e-mail e senha;
- depois que o primeiro ADM é criado, o cadastro é bloqueado automaticamente;
- a partir daí fica somente o login;
- corrigida a mensagem [object Object], exibindo o erro real.

SEGURANÇA:
Não existe cadastro público ilimitado de administradores.
Somente o PRIMEIRO administrador pode ser criado pela tela.
Novos administradores, se forem necessários futuramente, devem ser criados por uma função interna do ADM.

IMPORTANTE:
Se uma versão anterior já tiver criado um administrador automaticamente pelas variáveis
ADMIN_EMAIL/ADMIN_PASSWORD do Render, a tela de primeiro cadastro não aparecerá.
Nesse caso use essas credenciais ou remova/desative o bootstrap anterior antes de recriar.
