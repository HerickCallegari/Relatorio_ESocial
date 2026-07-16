# Relatorio de Inconsistencias eSocial

Aplicativo FastAPI para consultar Exporta Dados do SOC e exibir inconsistencias do eSocial em uma UI simples.

## Fontes SOC

- `192392`: Cadastro de Empresas
- `205226`: Inconsistencias S-2210, S-2220, S-2221, S-2230
- `218017`: Inconsistencias S-2240

## Configuracao local

1. Crie o ambiente virtual.
2. Instale as dependencias de `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Preencha as chaves do SOC e troque `APP_SECRET_KEY` e `ADMIN_PASSWORD`.
5. Execute:

```powershell
uvicorn main:app --reload
```

O primeiro usuario admin e criado automaticamente quando `ADMIN_USERNAME` e `ADMIN_PASSWORD` estiverem configurados e ainda nao existir usuario no banco.

