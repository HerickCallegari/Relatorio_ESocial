# Deploy em producao (Linux, sem Docker) — acesso por IP

Passo a passo copia-e-cola. Assume **Ubuntu/Debian** na VPS e acesso SSH com sudo.
O app roda em `/opt/safework/ESocial`, servido por uvicorn (systemd) na **porta 80**, com um
**timer diario** para o sync em massa. Banco **novo/limpo** (recomendado).

> Ao final voce acessa em `http://SEU_IP:8001`.
> (Porta 8001 porque nesta VPS a 80/8000/8080 ja sao de outros servicos Docker/nginx.
> Confira portas livres com `ss -tlnp`. Num servidor com a 80 livre, use a 80.)
> HTTPS fica para depois (precisa de dominio) — ver a secao final.
>
> Alem do ufw, pode existir um FIREWALL DE NUVEM (ex.: Hostinger) que bloqueia a porta
> de fora mesmo com o app rodando. Se `curl` local funciona mas o navegador nao abre,
> libere a porta no painel do provedor.

> **Rodando como root?** Se o seu prompt e `root@...`, **remova o `sudo`** de todos os
> comandos (e alguns servidores tem o `sudo` quebrado - "audit plugin"). Onde aparecer
> `sudo -u esocial <cmd>`, rode `<cmd>` direto como root; a posse e ajustada pelo `chown`.

---

## 0. Antes de comecar
- IP publico da VPS e acesso SSH (usuario com sudo).
- Tenha em maos os valores do SOC (os mesmos do `.env` de desenvolvimento):
  `SOC_EMPRESA`, e os codigos/chaves de 192392, 205226 e 218017.

## 1. Pacotes do sistema
```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install python3 python3-venv python3-pip unzip
sudo timedatectl set-timezone America/Sao_Paulo
```

## 2. Usuario e pasta do app
```bash
# cria a pasta (com o parent /opt/safework) e depois o usuario de servico:
sudo mkdir -p /opt/safework/ESocial
sudo useradd -r -s /usr/sbin/nologin -d /opt/safework/ESocial esocial
```

## 3. Enviar o codigo para a VPS
Na **sua maquina Windows** (PowerShell/Git Bash), a partir da pasta do projeto,
gere um zip **sem** venv/dados/segredos e envie:
```bash
# (na sua maquina, dentro de C:\SafeWork\ESocial)
# cria esocial.zip excluindo o que nao vai para producao:
powershell -Command "Compress-Archive -Path app,scripts,deploy,main.py,requirements.txt -DestinationPath esocial.zip -Force"

# envia para a VPS (troque USUARIO@SEU_IP):
scp esocial.zip USUARIO@SEU_IP:/tmp/
```
Na **VPS**, descompacte no lugar:
```bash
sudo unzip -o /tmp/esocial.zip -d /opt/safework/ESocial
```
> Observacao: NAO envie o `.env` de desenvolvimento. Vamos criar um novo (passo 5),
> com segredos fortes. O banco tambem sera novo (nao copie `data/`).

## 4. venv + dependencias
Cria o venv como root e, no fim (passo 5), o `chown` passa a posse para o `esocial`.
```bash
cd /opt/safework/ESocial
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```
> Se der erro tipo *ensurepip is not available*: `apt update && apt install -y python3-venv python3-pip` e repita.

## 5. Arquivo .env de producao (segredos FORTES)
Gere uma secret key forte:
```bash
/opt/safework/ESocial/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Crie o `.env` (troque os valores; use uma senha de admin forte de verdade):
```bash
sudo -u esocial tee /opt/safework/ESocial/.env >/dev/null <<'EOF'
APP_SECRET_KEY=COLE_A_SECRET_KEY_GERADA_ACIMA
DATABASE_URL=sqlite:///./data/app.db

ADMIN_USERNAME=admin
ADMIN_PASSWORD=TROQUE_POR_UMA_SENHA_FORTE

SOC_BASE_URL=https://ws1.soc.com.br/WebSoc/exportadados
SOC_EMPRESA=289501

SOC_EMPRESAS_CODIGO=192392
SOC_EMPRESAS_CHAVE=COLE_A_CHAVE

SOC_INCONSISTENCIAS_GERAIS_CODIGO=205226
SOC_INCONSISTENCIAS_GERAIS_CHAVE=COLE_A_CHAVE

SOC_INCONSISTENCIAS_2240_CODIGO=218017
SOC_INCONSISTENCIAS_2240_CHAVE=COLE_A_CHAVE
EOF

# protege o arquivo (contem segredos) e garante o dono:
sudo chown -R esocial:esocial /opt/safework/ESocial
sudo chmod 600 /opt/safework/ESocial/.env
```
> `SOC_WS_USUARIO`/`SOC_WS_PASSWORD` nao sao mais necessarios (o app nao usa mais).

## 6. Servico web (systemd)
```bash
sudo cp /opt/safework/ESocial/deploy/systemd/esocial-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now esocial-web.service
sudo systemctl status esocial-web.service --no-pager
```
Teste local (deve responder 200/redirect):
```bash
curl -I http://127.0.0.1/login
```

## 7. Timer diario do sync em massa
```bash
sudo cp /opt/safework/ESocial/deploy/systemd/esocial-bulk-sync.service /etc/systemd/system/
sudo cp /opt/safework/ESocial/deploy/systemd/esocial-bulk-sync.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now esocial-bulk-sync.timer
systemctl list-timers | grep esocial
```

## 8. Firewall
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp   # ja libera p/ quando tiver HTTPS
sudo ufw --force enable
sudo ufw status
```

## 9. Primeiro acesso e carga inicial
1. Abra `http://SEU_IP` no navegador.
2. Login: `admin` + a senha que voce definiu no `.env`.
   (Na 1a subida com banco vazio, o app cria as tabelas e o usuario admin sozinho.)
3. Clique em **Sincronizar empresas** (rapido; traz as ~3467 empresas).
4. Clique em **Atualizar dados** para a 1a carga de inconsistencias
   (roda em segundo plano, ~1,4-4h) — ou espere o timer das 02:00.

## 10. Comandos uteis
```bash
# logs do site:
journalctl -u esocial-web.service -f
# logs do sync diario:
journalctl -u esocial-bulk-sync.service -f
# rodar o sync agora (teste rapido com 5 empresas):
sudo -u esocial /opt/safework/ESocial/.venv/bin/python /opt/safework/ESocial/scripts/run_bulk_sync.py --limite 5
# reiniciar o site apos atualizar o codigo:
sudo systemctl restart esocial-web.service
```

## 11. Atualizar o codigo depois (deploy de nova versao)
```bash
# na sua maquina: gerar novo zip e enviar (passo 3), depois na VPS:
sudo unzip -o /tmp/esocial.zip -d /opt/safework/ESocial
sudo chown -R esocial:esocial /opt/safework/ESocial
sudo systemctl restart esocial-web.service
```
> O `.env` e o `data/` NAO sao sobrescritos (nao estao no zip).

## 12. Proximo passo: HTTPS (quando tiver dominio)
Com um dominio apontando para o IP, o mais simples e trocar o servico web para
`127.0.0.1:8000` e por o **Caddy** na frente (HTTPS automatico). Me avise que eu
entrego o `Caddyfile` e ajusto o `esocial-web.service`.

> Enquanto for so IP + HTTP, evite expor dados sensiveis publicamente por muito
> tempo; priorize colocar o dominio + HTTPS.
