"""O projeto em si: pyproject coerente e README sem link quebrado."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

import video_manager

RAIZ = Path(__file__).resolve().parent.parent


def test_pyproject_declara_o_essencial():
    dados = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    projeto = dados["project"]
    for chave in ("name", "version", "description", "readme", "requires-python", "license"):
        assert projeto.get(chave), chave
    nomes = {re.split(r"[<>=!~ \[]", d)[0].lower() for d in projeto["dependencies"]}
    assert {"pyside6", "opencv-python", "pillow", "numpy"} <= nomes
    assert projeto["scripts"]["video-manager"] == "video_manager.__main__:main"
    # a versão está em dois lugares: os dois precisam andar juntos
    assert projeto["version"] == video_manager.__version__


def test_links_locais_dos_readmes_existem():
    quebrados = []
    for readme in ("README.md", "README.pt-BR.md"):
        texto = (RAIZ / readme).read_text(encoding="utf-8")
        alvos = re.findall(r"\]\(([^)\s]+)\)", texto) + re.findall(r'src="([^"]+)"', texto)
        for alvo in alvos:
            if re.match(r"[a-z]+:", alvo) or alvo.startswith("#"):
                continue
            if not (RAIZ / alvo.split("#")[0]).exists():
                quebrados.append(f"{readme}: {alvo}")
    assert quebrados == []


def _ruff() -> list[str] | None:
    if shutil.which("ruff"):
        return ["ruff"]
    if shutil.which("uvx"):
        return ["uvx", "ruff"]
    return None


@pytest.mark.skipif(_ruff() is None, reason="nem ruff nem uvx no PATH")
@pytest.mark.parametrize("argumentos", [["check", "."], ["format", "--check", "."]])
def test_ruff(argumentos):
    feito = subprocess.run(
        [*_ruff(), *argumentos], cwd=RAIZ, capture_output=True, text=True, timeout=300
    )
    assert feito.returncode == 0, feito.stdout + feito.stderr
