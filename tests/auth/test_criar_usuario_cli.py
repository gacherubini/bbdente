import subprocess
import sys


def test_o_script_explica_o_uso_quando_chamado_errado():
    resultado = subprocess.run(
        [sys.executable, "-m", "scripts.criar_usuario"],
        capture_output=True, text=True,
    )
    assert resultado.returncode == 64
    assert "criar_usuario" in resultado.stderr
