# Brscans Backend (Go)

Reescrita completa do backend em **Go**, substituindo integralmente a implementação anterior em Django.

## Stack

- Go 1.24+
- net/http (roteamento HTTP)
- Armazenamento em memória para entidades de domínio

## Executar localmente

```bash
go run ./cmd/server
```

Servidor padrão em `http://localhost:8080`.

## Endpoints principais

- `GET /healthz`
- CRUD:
  - `/manhwas`
  - `/chapters`
  - `/images`
  - `/comments`
  - `/notifications`
- Relacionamento:
  - `GET /manhwas/{id}/chapters`
- Wrapper:
  - `GET /wrapper?url=...`
- Auth/Favoritos:
  - `POST /auth/register`
  - `POST /auth/login`
  - `GET /auth/me`
  - `POST /auth/discord`
  - `POST /manhwas/{id}/favorite`
  - `DELETE /manhwas/{id}/favorite`
  - `GET /manhwas/{id}/is-favorite`
  - `GET /favorites`
- Schema/docs placeholders:
  - `GET /api/schema/`
  - `GET /api/swagger/`
  - `GET /api/redoc/`

## Testes

```bash
go test ./...
```
