MATRIX BET V5 — BACKEND REAL DE AUTENTICAÇÃO + BANCO

O que é real nesta V5
- Banco SQLite persistente
- Cadastro real no banco
- Senha armazenada com scrypt + salt
- Login validado no servidor
- Sessão por token aleatório de 48 bytes
- Sessões expiram em 12 horas
- Endpoint /api/me protegido
- Eventos e 136 eventos ao vivo servidos pela API
- Apostas DEMO registradas no banco
- Saldo DEMO persistente
- Audit log para cadastro, login e apostas demo
- Odds da aposta são recalculadas/validadas no servidor (não confia na odd enviada pelo navegador)

O que NÃO está nesta V5
- PIX real
- saque real
- dinheiro real
- KYC real
- feed real de odds
- liquidação real de resultados
- licença/regulação de operador

COMO RODAR
1. Instale Python 3.11+.
2. Abra terminal nesta pasta.
3. Execute:
   pip install -r requirements.txt
4. Depois:
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
5. Abra:
   http://localhost:8000

No Windows, depois de instalar as dependências, você também pode usar run_windows.bat.

SEGURANÇA
Esta base já separa frontend e backend e não guarda senha em texto puro.
Antes de produção real ainda seriam necessários HTTPS, secrets em ambiente,
rate limiting distribuído, backup, observabilidade, KYC, antifraude,
provedor de odds e integração com uma operação autorizada.
