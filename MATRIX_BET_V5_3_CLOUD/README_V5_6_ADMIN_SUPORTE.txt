MATRIX BET V5.6 - ADMIN + SUPORTE + SEGURANÇA

NOVO PAINEL ADMIN
https://SEU-DOMINIO/admin

Recursos do ADMIN:
- total de usuários
- usuários bloqueados
- total de apostas
- chamados abertos
- lista de usuários
- CPF somente mascarado
- saldo demo
- bloquear/desbloquear contas
- lista de apostas
- central de suporte
- responder chamado e alterar status

Para criar a conta ADMIN no Render, configure:
ADMIN_EMAIL
ADMIN_PASSWORD (mínimo 8 caracteres)
ADMIN_USERNAME

SUPORTE DO USUÁRIO
- botão Ajuda
- abrir chamado
- acompanhar status
- ver resposta do administrador

CONTA E SEGURANÇA
- alterar senha autenticado
- alterar e-mail com confirmação da senha atual
- "Esqueci minha senha"
- token temporário de 30 minutos

E-MAIL DE RECUPERAÇÃO
A V5.6 já tem suporte SMTP. Configure no Render:
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASSWORD
SMTP_FROM
PUBLIC_BASE_URL=https://matrix-bet.onrender.com

Se SMTP não estiver configurado, a solicitação de reset é registrada,
mas nenhum e-mail externo é enviado.

SEGURANÇA
- Admin nunca vê senha.
- Admin nunca recebe CPF completo; somente máscara.
- Senhas continuam com scrypt + salt.
- CPF continua salvo por hash + últimos dígitos.
- Contas antigas são preservadas por migração automática.

IMPORTANTE
Tudo relativo a saldo/apostas permanece DEMONSTRATIVO.
