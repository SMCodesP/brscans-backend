-- Só SELECT: lista capítulos duplicados/vazios criados em 02/11/2026 pela
-- descoberta (slug trocado pela fonte). NÃO apague nada: o capítulo vazio pode
-- ter sido o único registro de um capítulo de verdade.
--
-- Contagem (banco de produção, lida em 02/11/2026):
--   vazios criados em 02/11 ............ 1.428
--   duplicados de capítulo anterior ...... 1 (q1)
--   duplicados criados no mesmo dia ...... 2 (q4; 'Special Episode' 66/111
--     são episódios distintos, o 146 é duplicata real)
--   grupos com o mesmo número ............ 2 (q3; o 146 acima e dois
--     especiais do webtoons que só compartilham o número do episódio)
--
-- Uso: psql "$DATABASE_URL" -f duplicados_02_11.sql

-- 1) Grupos de duplicado: mesmo manhwa e título já existia antes de 02/11.
SELECT ch.manhwa_id,
       m.title                      AS manhwa,
       ch.id                        AS capitulo_novo,
       ch.slug                      AS slug_novo,
       ch.title                     AS titulo_novo,
       old.id                       AS capitulo_antigo,
       old.slug                     AS slug_antigo,
       old.created_at::date         AS criado_em
FROM manhwa_chapter ch
JOIN manhwa_manhwa m ON m.id = ch.manhwa_id
JOIN manhwa_chapter old ON old.manhwa_id = ch.manhwa_id
 AND old.id <> ch.id
 AND old.created_at::date <> DATE '2026-11-02'
 AND lower(old.title) = lower(ch.title)
WHERE ch.created_at::date = DATE '2026-11-02'
  AND NOT EXISTS (SELECT 1 FROM manhwa_page p WHERE p.chapter_id = ch.id)
ORDER BY ch.manhwa_id, ch.slug;

-- 2) Contagem por mangá dos capítulos vazios criados em 02/11.
SELECT m.id, m.title, m.source, count(*) AS vazios_02_11
FROM manhwa_chapter ch
JOIN manhwa_manhwa m ON m.id = ch.manhwa_id
WHERE ch.created_at::date = DATE '2026-11-02'
  AND NOT EXISTS (SELECT 1 FROM manhwa_page p WHERE p.chapter_id = ch.id)
GROUP BY m.id, m.title, m.source
ORDER BY vazios_02_11 DESC;

-- 3) Grupos com o mesmo número no mesmo mangá (renumeração ou duplicata).
--    regexp_match e não substring: o grupo de captura devolve só a parte
--    decimal ('1.3' viraria '.3' e '1' casaria com '1').
SELECT ch.manhwa_id,
       (regexp_match(lower(ch.title), '[0-9]+[.][0-9]+|[0-9]+'))[1] AS numero,
       string_agg(ch.slug, ', ' ORDER BY ch.slug)                   AS slugs
FROM manhwa_chapter ch
WHERE ch.created_at::date = DATE '2026-11-02'
  AND ch.title ~ '[0-9]'
GROUP BY 1, 2
HAVING count(*) > 1
ORDER BY 1;

-- 4) Mesmo título repetido entre os capítulos criados em 02/11 (a fonte
--    trocou o id no meio da execução). 'Special Episode' repete por ser o
--    título de episódios distintos — conferir o título antes de tratar.
SELECT ch.manhwa_id,
       lower(trim(ch.title))                       AS titulo,
       string_agg(ch.slug, ', ' ORDER BY ch.slug)  AS slugs
FROM manhwa_chapter ch
WHERE ch.created_at::date = DATE '2026-11-02'
GROUP BY 1, 2
HAVING count(*) > 1
ORDER BY 1;
