# Brscans Backend

API Django/DRF do BRScans. A Lambda (Zappa) só serve a API e o cron; o trabalho de
fundo roda na Lambda de trabalho `brscans-backend-worker`.

## Mapa

| Arquivo | O que faz |
| --- | --- |
| `manage.py`, `pyproject.toml`, `zappa_settings.json` | Entry point, dependências e as duas stages da Lambda (`dev` = API, `cron` = `sync_workers.handler` a cada 2 h). |
| `brscans/settings.py`, `urls.py` | Configuração (envs, S3, banco) e todas as rotas. |
| `brscans/manhwa/models.py` | `Manhwa`, `Chapter`, `Page`, `ImageVariants`, `Genre`, `Comment`, `Notification`, `ReadingHistory`, `ReadChapter`. |
| `brscans/manhwa/views/` | `manhwa_vw` (catálogo, busca, histórico), `chapter`, `manhwa_chapter`, `image` (PATCH do tradutor/filler), `panel`, `comment_vw`, `notification_vw`. |
| `brscans/manhwa/work.py` | Travas por capítulo/página: claim condicional, backoff, desistência (`work_status`). |
| `brscans/manhwa/tasks/` | `sync_chapter` (baixa e funde), `sync_chapters`, `images_variants` (merge, tradução, presign), `panel` (ações do painel), `sync_workers` (cron: descoberta + reparo), `translate_manhwa` (título/descrição). |
| `brscans/manhwa/source_migration.py`, `discord.py` | Migração de fonte (mesmo Manhwa) e aviso de capítulo pronto no Discord. |
| `brscans/wrapper/sources/` | Um parser por site (Generic/Madara cobre a maioria); `sources/__init__.py` mapeia host → classe. |
| `brscans/wrapper/health.py` | Check de fonte do painel (HTTP, desafio Cloudflare, capítulos). |
| `brscans/utils/` | `tasks.py` (disparo local no dev / invoke na Lambda de trabalho), `image*` (download, merge, contrato de path), `generate_presigned_url`. |
| `brscans/authentication/` | Registro, login, Discord, favoritos. |
| `brscans/manhwa/management/commands/` | `migrate_sources`, `cleanup_ghost_chapters`, `fix_thumbnails`, `translate_manhwas`. |
| `tests/` | Suíte sqlite (`python manage.py test tests`); nunca toca o banco/S3 configurados. |
