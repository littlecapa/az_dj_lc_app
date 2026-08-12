"""
Schach-Captcha für die Contact-Seite: Stellungen kommen aus ChessPosition
(fen als PK, valid_moves_regex als Antwortmuster). Ist die Tabelle leer,
wird beim ersten Aufruf automatisch die Morphy-Stellung als Startdatensatz
eingetragen. Bei jedem Seitenaufruf wird zufällig eine Stellung gewählt.
"""
import re

from .models import ChessPosition

CAPTCHA_QUESTION = "What is White's best move?"

# Seed-Stellung, falls die Tabelle noch leer ist.
DEFAULT_FEN = "kbK5/pp6/1P6/8/8/8/8/R7"
DEFAULT_VALID_MOVES_REGEX = r"^[RT]a6$"

def get_random_position() -> ChessPosition:
    """Liefert eine zufällige ChessPosition. Ist die Tabelle leer, wird zuerst
    die Morphy-Stellung als Startdatensatz angelegt."""
    if not ChessPosition.objects.exists():
        ChessPosition.objects.create(fen=DEFAULT_FEN, valid_moves_regex=DEFAULT_VALID_MOVES_REGEX)
    return ChessPosition.objects.order_by("?").first()


def is_captcha_answer_correct(position: ChessPosition, answer: str) -> bool:
    try:
        return bool(re.fullmatch(position.valid_moves_regex, (answer or "").strip(), re.IGNORECASE))
    except re.error:
        return False


def fen_to_board_rows(fen_placement: str) -> list:
    """
    8 Zeilen (Rang 8 → Rang 1), je 8 Felder
    {'piece_type': 'K'/'Q'/'R'/'B'/'N'/'P' oder '', 'color': 'w'/'b', 'light': bool}.

    piece_type ist immer Großbuchstaben (Figurenart); die Farbe steht separat
    in 'color', damit das Template pro Figurenart nur EIN SVG-Symbol braucht
    und es nur eingefärbt (nicht neu gezeichnet) wird — garantiert identische
    Größe/Form für Weiß und Schwarz statt uneinheitlicher Font-Glyphen.
    """
    rows = []
    for row_idx, rank_str in enumerate(fen_placement.split("/")):
        rank = 8 - row_idx
        squares = []
        file_idx = 0
        for char in rank_str:
            if char.isdigit():
                for _ in range(int(char)):
                    file_idx += 1
                    squares.append({"piece_type": "", "color": "", "light": (file_idx + rank) % 2 == 1})
            else:
                file_idx += 1
                squares.append({
                    "piece_type": char.upper(),
                    "color": "w" if char.isupper() else "b",
                    "light": (file_idx + rank) % 2 == 1,
                })
        rows.append(squares)
    return rows
