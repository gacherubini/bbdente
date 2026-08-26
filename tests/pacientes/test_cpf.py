"""CPF digitado na recepcao.

A regua e a MESMA do telefone: numero estranho entra marcado, nunca recusado nem
corrigido no chute. Quem cadastra esta com a pessoa na frente, e um digito ditado
errado nao pode travar o atendimento — vira marca em `revisar_motivo`.
"""

from app.pacientes.cpf import formatar, parecer_invalido, so_digitos


def test_guarda_so_os_digitos():
    assert so_digitos("529.982.247-25") == "52998224725"
    assert so_digitos("  529 982 247 25 ") == "52998224725"
    assert so_digitos(None) == ""


def test_formata_para_leitura():
    assert formatar("52998224725") == "529.982.247-25"


def test_o_que_nao_tem_11_digitos_volta_como_veio():
    """Nunca inventa digito para fazer caber, igual ao formatar() do telefone."""
    assert formatar("5299822") == "5299822"
    assert formatar("") == ""


def test_cpf_valido_nao_e_suspeito():
    # Dois CPFs de teste conhecidos, com digito verificador correto.
    assert parecer_invalido("529.982.247-25") is False
    assert parecer_invalido("111.444.777-35") is False


def test_digito_verificador_errado_e_suspeito():
    assert parecer_invalido("529.982.247-26") is True


def test_todos_os_digitos_iguais_e_suspeito():
    """'111.111.111-11' fecha na conta do digito verificador, e mesmo assim nao
    existe. Sem esta regra, o campo vazio digitado como 000.000.000-00 passaria."""
    assert parecer_invalido("111.111.111-11") is True
    assert parecer_invalido("000.000.000-00") is True


def test_quantidade_errada_de_digitos_e_suspeito():
    assert parecer_invalido("5299822") is True
    assert parecer_invalido("529982247251") is True


def test_campo_vazio_nao_e_suspeito():
    """Nao informar o CPF e legitimo — 30 anos de cadastro sem CPF estao no banco."""
    assert parecer_invalido("") is False
    assert parecer_invalido(None) is False
