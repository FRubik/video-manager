"""Ações da tela de revisão e as teclas que as disparam.

A tecla principal de cada ação é configurável e fica salva na config; os
atalhos em `extra` são alternativas fixas, sempre disponíveis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QKeySequence


@dataclass(frozen=True)
class Action:
    #: identificador usado como chave na config
    key: str
    label: str
    default: str
    #: atalhos adicionais, não editáveis
    extra: tuple[str, ...] = field(default=())


#: teclas agrupadas à esquerda do teclado, para operar com uma mão só
ACTIONS: tuple[Action, ...] = (
    Action("prev", "Vídeo anterior", "A", ("Left",)),
    Action("next", "Próximo vídeo", "D", ("Right", "Space")),
    Action("keep", "Manter", "E"),
    Action("delete", "Excluir", "Q", ("Del",)),
    Action("open", "Abrir no player", "G"),
    Action("zoom", "Zoom 1:1", "Z"),
)

#: aplicar a sessão nunca é remapeável: é a única ação destrutiva imediata
APPLY_KEYS: tuple[str, ...] = ("Return", "Enter")

DEFAULTS: dict[str, str] = {action.key: action.default for action in ACTIONS}


def canonical(sequence: str) -> str:
    """Forma canônica da tecla, para comparar 'del' e 'Del' como iguais."""
    return QKeySequence(sequence).toString()


def normalize(raw: dict | None) -> dict[str, str]:
    """Completa o que falta com os padrões e descarta chaves desconhecidas."""
    result = dict(DEFAULTS)
    for action in ACTIONS:
        value = (raw or {}).get(action.key)
        if isinstance(value, str) and canonical(value):
            result[action.key] = canonical(value)
    return result


def conflicts(mapping: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Teclas usadas por mais de uma ação, como (tecla, [rótulos])."""
    by_key: dict[str, list[str]] = {}
    for action in ACTIONS:
        sequence = canonical(mapping.get(action.key, ""))
        if sequence:
            by_key.setdefault(sequence, []).append(action.label)
    return [(seq, labels) for seq, labels in by_key.items() if len(labels) > 1]


def describe(mapping: dict[str, str]) -> str:
    """Linha de ajuda mostrada no rodapé da revisão."""
    parts = []
    for action in ACTIONS:
        keys = [mapping.get(action.key, "")] + [canonical(e) for e in action.extra]
        keys = [k for k in keys if k]
        parts.append(f"{'/'.join(keys)} {action.label.lower()}")
    parts.append("Enter aplica")
    return " · ".join(parts)
