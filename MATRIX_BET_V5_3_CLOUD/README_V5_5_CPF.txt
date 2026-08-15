MATRIX BET V5.5 - CADASTRO COM CPF

Alterações:
- Cadastro agora solicita Nome de usuário, E-mail, CPF e Senha.
- CPF validado pelos dois dígitos verificadores.
- CPF não é salvo em texto puro: o backend armazena hash SHA-256 + últimos 4 dígitos.
- CPF não pode ser usado em duas contas.
- Nome de usuário é validado e não pode estar em uso.
- Login continua por e-mail + senha.
- Migração automática acrescenta as colunas de CPF sem apagar contas existentes.
- Cache do PWA atualizado para V5.5.

IMPORTANTE:
Esta versão preserva o fluxo PWA e o mesmo endereço no Render.
Para produção real, adicione política de privacidade, consentimento LGPD, PostgreSQL persistente
e processo formal de verificação de identidade/KYC antes de operar com dinheiro real.
