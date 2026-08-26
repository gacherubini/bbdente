"""Migra a camada azul do odontograma: o que ja existia no dente antes.

Os 309 codigos de icone do Dentalis (OICO14, d01RX, d08i2...) nao foram traduzidos:
sabemos o dente e a frequencia, nao o significado. Ate a Dra. Katia interpretar —
cerca de 10 codigos cobrem quase tudo — entram como OUTRO com o codigo preservado.
Traduzir no chute seria inventar diagnostico.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinico.models import Condicao, Odontograma
from app.pacientes.models import Paciente
from app.shared.dentes import fdi_de_indice_legado
from app.shared.tipos import TipoCondicao
from migracao.extrato import Extrato
from migracao.texto import limpar


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> int:
    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    odontogramas = {
        (o.paciente_id, o.numero): o.id for o in sessao.scalars(select(Odontograma))
    }
    ja_existem = sessao.query(Condicao).count()
    if ja_existem:
        return ja_existem

    total = 0
    for linha in extrato.linhas("ARQICONE"):
        paciente_id = pacientes.get(limpar(linha["CODICLIE"]))
        if paciente_id is None:
            continue

        bruto = limpar(linha["NUMDENTE"]) or ""
        try:
            fdi = fdi_de_indice_legado(int(bruto))
        except ValueError:
            # ARQICONE tem NUMDENTE ate '88' (sentinela de tela). Sem dente real,
            # a condicao nao tem onde ser desenhada.
            continue

        numero_odo = int(float(linha["NUMODO"] or 1)) or 1
        chave = (paciente_id, numero_odo)
        if chave not in odontogramas:
            odontograma = Odontograma(paciente_id=paciente_id, numero=numero_odo)
            sessao.add(odontograma)
            sessao.flush()
            odontogramas[chave] = odontograma.id

        sessao.add(
            Condicao(
                odontograma_id=odontogramas[chave],
                dente=fdi,
                tipo=TipoCondicao.OUTRO,
                regioes=[],
                icone_legado=limpar(linha["ICONE"]),
            )
        )
        total += 1
        if total % 2_000 == 0:
            sessao.flush()

    sessao.flush()
    return total
