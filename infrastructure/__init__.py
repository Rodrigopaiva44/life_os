"""
infrastructure/
===============
Camada de Infraestrutura — adaptadores para recursos externos.

Contém:
  - settings.py   → configuração via pydantic-settings / .env
  - database.py   → engine SQLModel + session factory (PostgreSQL)
  - (futuro) repositories/  → implementações concretas dos repositórios
  - (futuro) excel/         → exportadores para Life_OS_V1.xlsx
"""
