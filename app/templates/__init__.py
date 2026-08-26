from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.shared.formato import moeda

templates = Jinja2Templates(directory=str(Path(__file__).parent))
templates.env.filters["moeda"] = moeda
