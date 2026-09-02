# POC 16 — origem do raw

O backend agora gera o destino do raw como `.webp` e assina
`Content-Type: image/webp`, igual aos bytes enviados pelo translator. O helper
também cobre JPEG e PNG e evita dividir uma pasta string caractere por caractere.

A decisão consolidada e a matriz ponta a ponta ficam na branch homônima do
`brscans-translator`.
