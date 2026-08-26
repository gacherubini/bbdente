from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.shared.formato import moeda

ESTATICOS = Path(__file__).parent.parent / "static"

templates = Jinja2Templates(directory=str(Path(__file__).parent))
templates.env.filters["moeda"] = moeda


@lru_cache(maxsize=32)
def estatico(nome: str) -> str:
    """'/static/bddente.css?v=...' — o mesmo arquivo, com uma marca que muda a
    cada deploy.

    Sem isso o navegador guarda o CSS e o JavaScript antigos e a tela aparece
    quebrada depois de cada atualizacao, ate alguem saber que precisa forcar a
    recarga. Numa clinica ninguem sabe.

    A marca vem do tamanho e da data do arquivo: dentro da imagem do Docker as
    duas sao iguais em qualquer maquina da mesma versao, e mudam quando o
    arquivo muda. Resolvido uma vez por arquivo, no primeiro uso.
    """
    arquivo = ESTATICOS / nome
    try:
        estado = arquivo.stat()
        marca = f"{int(estado.st_mtime)}{estado.st_size}"
    except OSError:
        # Arquivo ausente e problema de deploy, nao motivo para derrubar a tela:
        # sai sem marca e o navegador resolve como sempre resolveu.
        return f"/static/{nome}"
    return f"/static/{nome}?v={marca}"


templates.env.globals["estatico"] = estatico
