# Agendamento diario do sync (systemd)

Roda `scripts/run_bulk_sync.py` uma vez por dia, em processo isolado do servidor web.
A UI acompanha o progresso pelo mesmo banco (SQLite em WAL).

> Ajuste os caminhos/usuario nos arquivos `.service` conforme o seu deploy.
> Exemplo assume o projeto em `/opt/safework/ESocial`, venv em `/opt/safework/ESocial/.venv`,
> `.env` e `data/` dentro de `/opt/safework/ESocial`, e usuario `esocial`.

## 1. Pre-requisitos no deploy
- Projeto em `/opt/safework/ESocial` (com `main.py`, `app/`, `scripts/`, `.env`, `data/`).
- venv criado: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- (Recomendado) usuario dedicado sem shell:
  ```bash
  sudo useradd -r -s /usr/sbin/nologin esocial
  sudo chown -R esocial:esocial /opt/safework/ESocial
  ```
- Timezone do servidor (para "02:00" ser horario local):
  ```bash
  sudo timedatectl set-timezone America/Sao_Paulo
  ```

## 2. Instalar as units
```bash
sudo cp deploy/systemd/esocial-bulk-sync.service /etc/systemd/system/
sudo cp deploy/systemd/esocial-bulk-sync.timer   /etc/systemd/system/
# revise User/Group/WorkingDirectory/ExecStart no .service antes:
sudo nano /etc/systemd/system/esocial-bulk-sync.service

sudo systemctl daemon-reload
sudo systemctl enable --now esocial-bulk-sync.timer
```

## 3. Verificar
```bash
# proxima execucao agendada:
systemctl list-timers | grep esocial
# estado do timer:
systemctl status esocial-bulk-sync.timer
```

## 4. Testar agora (sem esperar 02:00)
```bash
# dispara o job manualmente e acompanha o log ao vivo:
sudo systemctl start esocial-bulk-sync.service
journalctl -u esocial-bulk-sync.service -f
```
Para um teste rapido com poucas empresas, rode direto o script:
```bash
sudo -u esocial /opt/safework/ESocial/.venv/bin/python /opt/safework/ESocial/scripts/run_bulk_sync.py --limite 5
```

## 5. Logs / historico de execucoes
```bash
journalctl -u esocial-bulk-sync.service            # tudo
journalctl -u esocial-bulk-sync.service --since today
```

## Notas
- **Sem sobreposicao:** `Type=oneshot` faz o systemd nao iniciar uma 2a execucao
  enquanto a atual roda. O app ainda tem a trava propria (um job por vez).
- **Retomada:** se a execucao cair no meio, a proxima (manual ou do dia seguinte)
  continua de onde parou (empresas ja sincronizadas nas ultimas 20h sao puladas).
- **Resolvidas:** a cada execucao, inconsistencias que nao voltam do SOC sao removidas
  (hard delete), como definido.
- **Cancelar:** pela tela do app (botao Cancelar) ou marcando o job como 'cancelando';
  este processo para no proximo item.
