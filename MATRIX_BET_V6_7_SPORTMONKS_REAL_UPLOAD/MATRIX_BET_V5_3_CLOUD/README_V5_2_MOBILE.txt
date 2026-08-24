MATRIX BET V5.2 MOBILE

Esta versão mantém o backend V5/V5.1 e melhora o uso no celular.

MOBILE
- Barra inferior fixa: Início | Futebol | Ao Vivo | Apostas | Carteira
- Botões de odds maiores para toque
- Tabelas compactadas sem esconder as 3 odds principais
- Cupom acessível por botão flutuante
- Cupom abre como painel inferior
- 136 eventos Ao Vivo continuam vindo da API
- Login/cadastro/saldo continuam validados pelo backend

NO NOTEBOOK
1. Pare o servidor antigo com CTRL+C.
2. Extraia a V5.2.
3. Dê dois cliques em run_windows.bat.
4. Abra http://localhost:8000

NO CELULAR NA MESMA REDE WI-FI
localhost NÃO funciona no celular.
Você deve usar o IP do notebook, por exemplo:
http://192.168.0.15:8000

Para descobrir o IP no Windows:
1. Abra CMD.
2. Digite: ipconfig
3. Procure "Endereço IPv4" da conexão Wi-Fi.
4. No celular, abra http://SEU-IP:8000

Se o Windows perguntar sobre Firewall, permita acesso em redes privadas.
