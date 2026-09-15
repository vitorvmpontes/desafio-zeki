# data/sample/

Uma amostra pequena (um a dois meses) dos dados já processados, pensada para quem for avaliar o projeto rodar uma demonstração rápida sem precisar baixar o dataset completo da ANEEL (que passa de 250 MB por ano).

**Ainda não populada.** Gerar essa amostra requer rodar `etl/download.py` contra os servidores reais da ANEEL, o que precisa de uma rede sem restrições — o ambiente de desenvolvimento deste projeto não tem esse acesso (ver `etl/README.md`). Assim que o pipeline rodar com dados reais (na sua máquina ou no GitHub Actions), um recorte pequeno do resultado será versionado aqui.

Enquanto isso, `tests/fixtures/sample_raw_interrupcoes.csv` cobre o mesmo papel para desenvolvimento e testes — mas é sintética (eventos fictícios, municípios reais), não deve ser confundida com uma amostra dos dados reais da ANEEL.
