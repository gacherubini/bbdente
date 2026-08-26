"""Reune todos os modelos num lugar so, para que o Alembic e o mapeador do
SQLAlchemy enxerguem o metadata completo.

Este e o UNICO arquivo do projeto onde modelos de modulos diferentes se encontram.
Importar `app.auth.models` de dentro de `app/clinico/` continua sendo violacao da
fronteira de modulo.
"""

from app.auth import models as auth_models
from app.catalogo import models as catalogo_models
from app.clinico import models as clinico_models
from app.pacientes import models as pacientes_models

__all__ = ["auth_models", "catalogo_models", "clinico_models", "pacientes_models"]
