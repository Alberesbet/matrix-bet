MATRIX BET V5.3 CLOUD

OBJETIVO
Esta versão foi preparada para ficar online em um servidor público.
Depois do deploy, os usuários acessam por um link HTTPS público e NÃO
precisam estar no mesmo Wi-Fi nem com o notebook ligado.

O QUE CONTINUA DEMONSTRATIVO
- saldo
- apostas
- eventos
- odds
- 136 eventos ao vivo

O QUE FOI PREPARADO PARA CLOUD
- FastAPI
- PostgreSQL via DATABASE_URL
- SQLite automático quando rodar localmente sem DATABASE_URL
- Dockerfile
- render.yaml
- railway.toml
- endpoint /health
- cadastro/login persistentes no PostgreSQL
- sessões persistentes no PostgreSQL
- apostas demo persistentes no PostgreSQL

TESTE LOCAL
1. pip install -r requirements.txt
2. run_windows.bat
3. abra http://localhost:8000

RENDER
1. Coloque esta pasta em um repositório GitHub.
2. No Render, crie um Blueprint a partir do repositório.
3. O arquivo render.yaml cria o Web Service e o PostgreSQL.
4. Após o deploy, abra a URL onrender.com gerada.

RAILWAY
1. Coloque a pasta em um repositório GitHub.
2. Crie projeto no Railway a partir do repositório.
3. Adicione PostgreSQL ao projeto.
4. No serviço web, defina DATABASE_URL usando a variável do PostgreSQL.
5. Gere um Domain na seção Networking.

IMPORTANTE
Esta versão é para DEMONSTRAÇÃO ONLINE.
Não habilita depósitos, PIX, saques ou apostas com dinheiro real.
