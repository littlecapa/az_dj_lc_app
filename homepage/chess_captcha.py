"""
Schach-Captcha für die Contact-Seite: feste Stellung, Nutzer muss den besten
Zug für Weiß nennen. Kein externer Captcha-Anbieter, kein Tracking — filtert
generische Spam-Bots, die Formularfelder blind ausfüllen.
"""
CAPTCHA_FEN_PLACEMENT = "kbK5/pp6/1P6/8/8/8/8/R7"
CAPTCHA_QUESTION = "What is White's best move?"

# Groß-/Kleinschreibung wird ignoriert; "r" (engl. Rook) und "t" (dt. Turm) beide akzeptiert.
CAPTCHA_ACCEPTED_ANSWERS = {"ra6", "ta6"}

_PIECE_GLYPHS = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


def is_captcha_answer_correct(answer: str) -> bool:
    return (answer or "").strip().lower() in CAPTCHA_ACCEPTED_ANSWERS


def fen_to_board_rows(fen_placement: str = CAPTCHA_FEN_PLACEMENT) -> list:
    """8 Zeilen (Rang 8 → Rang 1), je 8 Felder {'piece': Glyph oder '', 'light': bool}."""
    rows = []
    for row_idx, rank_str in enumerate(fen_placement.split("/")):
        rank = 8 - row_idx
        squares = []
        file_idx = 0
        for char in rank_str:
            if char.isdigit():
                for _ in range(int(char)):
                    file_idx += 1
                    squares.append({"piece": "", "light": (file_idx + rank) % 2 == 1})
            else:
                file_idx += 1
                squares.append({"piece": _PIECE_GLYPHS.get(char, ""), "light": (file_idx + rank) % 2 == 1})
        rows.append(squares)
    return rows
