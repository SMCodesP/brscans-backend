# Brscans Backend

O **Brscans Backend** é uma aplicação baseada em **Django** que realiza o scraping de sites de mangás, clonando o conteúdo e integrando com o **Brscans Translator** para traduzir os balões de fala. Toda a estrutura é otimizada para escalabilidade, utilizando **AWS S3** para armazenamento, **AWS Lambda** para execução serverless e **Zappa** para implantação.

## Funcionalidades

- **Scraper de sites de mangá**: Coleta imagens e dados dos capítulos.
- **Clonagem de sites**: Replica a estrutura do site original.
- **Integração com o Brscans Translator**: Envia imagens para tradução automatizada.
- **Armazenamento em S3**: Gerencia os arquivos de forma escalável.
- **Execução Serverless**: Utiliza AWS Lambda e Zappa para rodar de forma eficiente.

## Tecnologias utilizadas

- **Django** e **Django REST Framework**
- **BeautifulSoup** e **Scrapy** para scraping
- **AWS S3** para armazenamento de imagens
- **AWS Lambda** para execução assíncrona
- **Zappa** para deploy serverless
<!-- 
// "events": [
//     {
//         "function": "brscans.manhwa.tasks.sync_manhwas.sync_manhwas",
//         "expression": "cron(0/30 * * * ? *)"
//     }
// ]
-->