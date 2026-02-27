"""
application/
============
Camada de Aplicação — casos de uso e orquestração de negócio.

Responsabilidade: coordenar domain + infrastructure sem conter lógica de UI.
Cada módulo aqui representa um "use case" ou "command handler".

Estrutura planejada:
  services/
    faculdade_service.py    → adicionar matéria, registrar falta, alertar risco
    work_service.py         → criar task, mover status, priorizar backlog
    financeiro_service.py   → registrar transação, calcular P&L, exportar ledger
    investimento_service.py → atualizar posição, calcular preço médio ponderado
    saude_service.py        → registrar refeição, calcular deficit calórico diário

  (futuro) ai_tools.py      → Function Calling schemas para o Agente de IA via Telegram
"""
