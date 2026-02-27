"""
presentation/
=============
Camada de Apresentação — interfaces externas de entrada/saída.

Responsabilidade: transformar comandos externos em calls da camada Application.
Não contém lógica de negócio.

Estrutura planejada:
  telegram/
    bot.py          → entrypoint do bot; roteamento de comandos e mensagens
    handlers.py     → handlers mapeados para application services
    schemas.py      → payloads de Function Calling (OpenAI / Gemini)

  streamlit/
    app.py          → dashboard visual do Life_OS
    pages/          → Work_Projetos, Financeiro, Saúde, Faculdade

  (futuro) api/
    router.py       → FastAPI routers para exposição via HTTP
"""
