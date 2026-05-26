from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.logging import get_logger


_EMPTY = " "
_WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


@dataclass
class TicTacToeResult:
    response: str
    context: dict


class TicTacToeService:
    _context_key = "tic_tac_toe"
    _position_labels = {
        1: "Top Left",
        2: "Top Center",
        3: "Top Right",
        4: "Middle Left",
        5: "Middle Center",
        6: "Middle Right",
        7: "Bottom Left",
        8: "Bottom Center",
        9: "Bottom Right",
    }

    def __init__(self) -> None:
        self._logger = get_logger("uvicorn.error")

    def should_handle(self, message: str, thread_context: dict | None) -> bool:
        text = message.strip().lower()
        if text.startswith("/ttt"):
            return True
        if self._looks_like_start_request(text):
            return True
        state = self._extract_state(thread_context)
        if state.get("active") and self._extract_move_position(text) is not None:
            return True
        return False

    def process_message(
        self,
        message: str,
        thread_context: dict | None,
        *,
        user_email: str | None = None,
        thread_id: str | None = None,
    ) -> TicTacToeResult:
        text = message.strip().lower()
        context = dict(thread_context or {})
        state = self._extract_state(context)
        self._logger.info(
            "ttt_message_received | user=%s | thread_id=%s | active=%s | input=%s",
            user_email or "unknown",
            thread_id or "unknown",
            state.get("active", False),
            text,
        )

        if self._looks_like_start_request(text):
            return self._start_new_game(context)

        if text.startswith("/ttt"):
            command = text[4:].strip()
            if command in {"", "help"}:
                self._logger.info(
                    "ttt_help_requested | user=%s | thread_id=%s | active=%s",
                    user_email or "unknown",
                    thread_id or "unknown",
                    state.get("active", False),
                )
                return TicTacToeResult(response=self._help_text(state.get("active", False)), context=context)
            if command in {"start", "new", "restart"}:
                return self._start_new_game(context, user_email=user_email, thread_id=thread_id)
            if command in {"board", "show"}:
                if not state.get("active"):
                    return TicTacToeResult(
                        response="No active game. Start one with `/ttt start`.",
                        context=context,
                    )
                self._logger.info(
                    "ttt_board_requested | user=%s | thread_id=%s | board=%s",
                    user_email or "unknown",
                    thread_id or "unknown",
                    self._compact_board(list(state["board"])),
                )
                return TicTacToeResult(response=self._render_state(state), context=context)
            if command in {"stop", "quit", "end"}:
                state = self._new_state(active=False)
                context[self._context_key] = state
                self._logger.info(
                    "ttt_game_stopped | user=%s | thread_id=%s",
                    user_email or "unknown",
                    thread_id or "unknown",
                )
                return TicTacToeResult(
                    response="Game ended. Start a new one anytime with `/ttt start`.",
                    context=context,
                )

            move = self._extract_move_position(command)
            if move is None:
                return TicTacToeResult(
                    response="Invalid Tic Tac Toe command. Use `/ttt help`.",
                    context=context,
                )
            return self._handle_move(
                context,
                state,
                move,
                user_email=user_email,
                thread_id=thread_id,
            )

        move = self._extract_move_position(text)
        if move is None:
            return TicTacToeResult(response=self._help_text(state.get("active", False)), context=context)
        return self._handle_move(
            context,
            state,
            move,
            user_email=user_email,
            thread_id=thread_id,
        )

    def _handle_move(
        self,
        context: dict,
        state: dict,
        position: int,
        *,
        user_email: str | None = None,
        thread_id: str | None = None,
    ) -> TicTacToeResult:
        if not state.get("active"):
            self._logger.info(
                "ttt_move_rejected_no_active_game | user=%s | thread_id=%s | move=%s",
                user_email or "unknown",
                thread_id or "unknown",
                position,
            )
            return TicTacToeResult(
                response="No active game. Start one with `/ttt start`.",
                context=context,
            )

        board = list(state.get("board", [_EMPTY] * 9))
        index = position - 1
        if index < 0 or index > 8:
            self._logger.info(
                "ttt_move_rejected_out_of_range | user=%s | thread_id=%s | move=%s",
                user_email or "unknown",
                thread_id or "unknown",
                position,
            )
            return TicTacToeResult(response="Move must be a number from 1 to 9.", context=context)
        if board[index] != _EMPTY:
            self._logger.info(
                "ttt_move_rejected_occupied | user=%s | thread_id=%s | move=%s | board=%s",
                user_email or "unknown",
                thread_id or "unknown",
                position,
                self._compact_board(board),
            )
            return TicTacToeResult(
                response=f"Cell {position} is already occupied. Choose another move.\n\n{self._render_board(board)}",
                context=context,
            )

        user_symbol = state.get("user_symbol", "X")
        agent_symbol = state.get("agent_symbol", "O")
        board[index] = user_symbol
        move_number = int(state.get("move_count", 0)) + 1
        state["move_count"] = move_number
        self._log_pretty_move(
            actor="PLAYER",
            move_number=move_number,
            position=position,
            board=board,
            user_email=user_email,
            thread_id=thread_id,
        )
        self._logger.info(
            "ttt_user_move | user=%s | thread_id=%s | move=%s | board=%s",
            user_email or "unknown",
            thread_id or "unknown",
            position,
            self._compact_board(board),
        )

        winner = self._winner(board)
        if winner == user_symbol:
            ended = self._new_state(active=False)
            ended["board"] = board
            ended["winner"] = user_symbol
            context[self._context_key] = ended
            self._log_result_banner(
                result="🏆 PLAYER WIN",
                board=board,
                user_email=user_email,
                thread_id=thread_id,
            )
            self._logger.info(
                "ttt_game_finished | user=%s | thread_id=%s | result=user_win | board=%s",
                user_email or "unknown",
                thread_id or "unknown",
                self._compact_board(board),
            )
            return TicTacToeResult(
                response=f"You win.\n\n{self._render_board(board)}\n\nStart a new round with `/ttt start`.",
                context=context,
            )
        if self._is_draw(board):
            ended = self._new_state(active=False)
            ended["board"] = board
            ended["winner"] = "draw"
            context[self._context_key] = ended
            self._log_result_banner(
                result="🤝 DRAW",
                board=board,
                user_email=user_email,
                thread_id=thread_id,
            )
            self._logger.info(
                "ttt_game_finished | user=%s | thread_id=%s | result=draw_after_user_move | board=%s",
                user_email or "unknown",
                thread_id or "unknown",
                self._compact_board(board),
            )
            return TicTacToeResult(
                response=f"It's a draw.\n\n{self._render_board(board)}\n\nStart a new round with `/ttt start`.",
                context=context,
            )

        agent_move = self._best_move(board, agent_symbol, user_symbol)
        if agent_move is not None:
            board[agent_move] = agent_symbol
            self._log_pretty_move(
                actor="AGENT",
                move_number=move_number,
                position=agent_move + 1,
                board=board,
                user_email=user_email,
                thread_id=thread_id,
            )
            self._logger.info(
                "ttt_agent_move | user=%s | thread_id=%s | move=%s | board=%s",
                user_email or "unknown",
                thread_id or "unknown",
                agent_move + 1,
                self._compact_board(board),
            )

        winner = self._winner(board)
        if winner == agent_symbol:
            ended = self._new_state(active=False)
            ended["board"] = board
            ended["winner"] = agent_symbol
            context[self._context_key] = ended
            self._log_result_banner(
                result="🤖 AGENT WIN",
                board=board,
                user_email=user_email,
                thread_id=thread_id,
            )
            self._logger.info(
                "ttt_game_finished | user=%s | thread_id=%s | result=agent_win | board=%s",
                user_email or "unknown",
                thread_id or "unknown",
                self._compact_board(board),
            )
            return TicTacToeResult(
                response=(
                    f"I played {agent_move + 1}. I win this round.\n\n"
                    f"{self._render_board(board)}\n\n"
                    "Start a new round with `/ttt start`."
                ),
                context=context,
            )
        if self._is_draw(board):
            ended = self._new_state(active=False)
            ended["board"] = board
            ended["winner"] = "draw"
            context[self._context_key] = ended
            self._log_result_banner(
                result="🤝 DRAW",
                board=board,
                user_email=user_email,
                thread_id=thread_id,
            )
            self._logger.info(
                "ttt_game_finished | user=%s | thread_id=%s | result=draw_after_agent_move | board=%s",
                user_email or "unknown",
                thread_id or "unknown",
                self._compact_board(board),
            )
            return TicTacToeResult(
                response=(
                    f"I played {agent_move + 1}. It's a draw.\n\n"
                    f"{self._render_board(board)}\n\n"
                    "Start a new round with `/ttt start`."
                ),
                context=context,
            )

        state["board"] = board
        state["active"] = True
        state["winner"] = None
        context[self._context_key] = state
        self._logger.info(
            "ttt_game_continues | user=%s | thread_id=%s | board=%s",
            user_email or "unknown",
            thread_id or "unknown",
            self._compact_board(board),
        )
        return TicTacToeResult(
            response=(
                f"I played {agent_move + 1}. Your turn.\n\n"
                f"{self._render_board(board)}\n\n"
                "Play your move with `/ttt <1-9>` or just send a number."
            ),
            context=context,
        )

    def _start_new_game(
        self,
        context: dict,
        *,
        user_email: str | None = None,
        thread_id: str | None = None,
    ) -> TicTacToeResult:
        state = self._new_state(active=True)
        context[self._context_key] = state
        self._logger.info("\n🕹️ NEW TIC TAC TOE GAME STARTED\n")
        self._logger.info("🧠 Current board state:\n%s\n", self._pretty_board(list(state["board"])))
        self._logger.info(
            "ttt_game_started | user=%s | thread_id=%s | board=%s",
            user_email or "unknown",
            thread_id or "unknown",
            self._compact_board(list(state["board"])),
        )
        return TicTacToeResult(
            response=(
                "New Tic Tac Toe game started. You are **X** and I am **O**.\n\n"
                f"{self._render_board(state['board'])}\n\n"
                "Choose your first move with `/ttt <1-9>` or just send a number."
            ),
            context=context,
        )

    def _new_state(self, active: bool) -> dict:
        return {
            "active": active,
            "board": [_EMPTY] * 9,
            "user_symbol": "X",
            "agent_symbol": "O",
            "move_count": 0,
            "winner": None,
        }

    def _extract_state(self, thread_context: dict | None) -> dict:
        state = dict((thread_context or {}).get(self._context_key) or {})
        board = state.get("board")
        if not isinstance(board, list) or len(board) != 9:
            state["board"] = [_EMPTY] * 9
        state.setdefault("active", False)
        state.setdefault("user_symbol", "X")
        state.setdefault("agent_symbol", "O")
        state.setdefault("move_count", 0)
        state.setdefault("winner", None)
        return state

    def _help_text(self, active: bool) -> str:
        if active:
            return (
                "Tic Tac Toe commands:\n"
                "- `/ttt <1-9>` to play a move\n"
                "- send `1`..`9` directly to play\n"
                "- `/ttt board` to show current board\n"
                "- `/ttt restart` to restart\n"
                "- `/ttt stop` to end game"
            )
        return (
            "Start Tic Tac Toe with `/ttt start`.\n"
            "Then play using `/ttt <1-9>` (or just send a number)."
        )

    def _render_state(self, state: dict) -> str:
        suffix = "Your turn." if state.get("active") else "No active game."
        return f"{self._render_board(list(state['board']))}\n\n{suffix}"

    def _render_board(self, board: list[str]) -> str:
        cells = [cell if cell != _EMPTY else str(i + 1) for i, cell in enumerate(board)]
        return (
            "| "
            + " | ".join(cells[0:3])
            + " |\n|---|---|---|\n| "
            + " | ".join(cells[3:6])
            + " |\n|---|---|---|\n| "
            + " | ".join(cells[6:9])
            + " |"
        )

    def _compact_board(self, board: list[str]) -> str:
        return "".join(cell if cell != _EMPTY else "-" for cell in board)

    def _pretty_board(self, board: list[str]) -> str:
        rows = [board[0:3], board[3:6], board[6:9]]
        pretty_rows = [" | ".join(cell if cell != _EMPTY else " " for cell in row) for row in rows]
        return "\n--------\n".join(pretty_rows)

    def _log_pretty_move(
        self,
        *,
        actor: str,
        move_number: int,
        position: int,
        board: list[str],
        user_email: str | None,
        thread_id: str | None,
    ) -> None:
        position_label = self._position_labels.get(position, f"Cell {position}")
        self._logger.info(
            "\n%s MOVE #%s\n📍 Position: %s\n🧠 Current board state:\n%s\n",
            actor,
            move_number,
            position_label,
            self._pretty_board(board),
            extra={"user_email": user_email or "unknown", "thread_id": thread_id or "unknown"},
        )

    def _log_result_banner(
        self,
        *,
        result: str,
        board: list[str],
        user_email: str | None,
        thread_id: str | None,
    ) -> None:
        self._logger.info(
            "\n%s\n🧠 Final board state:\n%s\n",
            result,
            self._pretty_board(board),
            extra={"user_email": user_email or "unknown", "thread_id": thread_id or "unknown"},
        )

    def _extract_move_position(self, text: str) -> int | None:
        stripped = text.strip().lower()
        if re.fullmatch(r"[1-9]", stripped):
            return int(stripped)
        match = re.fullmatch(r"(?:move\s+)?([1-9])", stripped)
        if match:
            return int(match.group(1))
        return None

    def _looks_like_start_request(self, text: str) -> bool:
        return "tic tac toe" in text and any(word in text for word in ("play", "start", "new"))

    def _winner(self, board: list[str]) -> str | None:
        for a, b, c in _WIN_LINES:
            if board[a] != _EMPTY and board[a] == board[b] == board[c]:
                return board[a]
        return None

    def _is_draw(self, board: list[str]) -> bool:
        return self._winner(board) is None and all(cell != _EMPTY for cell in board)

    def _best_move(self, board: list[str], agent_symbol: str, user_symbol: str) -> int | None:
        available = [idx for idx, cell in enumerate(board) if cell == _EMPTY]
        if not available:
            return None

        best_score = -999
        best_idx = available[0]
        for idx in available:
            board[idx] = agent_symbol
            score = self._minimax(board, False, agent_symbol, user_symbol)
            board[idx] = _EMPTY
            if score > best_score:
                best_score = score
                best_idx = idx
        return best_idx

    def _minimax(self, board: list[str], is_max: bool, agent_symbol: str, user_symbol: str) -> int:
        winner = self._winner(board)
        if winner == agent_symbol:
            return 1
        if winner == user_symbol:
            return -1
        if self._is_draw(board):
            return 0

        available = [idx for idx, cell in enumerate(board) if cell == _EMPTY]
        if is_max:
            best = -999
            for idx in available:
                board[idx] = agent_symbol
                best = max(best, self._minimax(board, False, agent_symbol, user_symbol))
                board[idx] = _EMPTY
            return best

        best = 999
        for idx in available:
            board[idx] = user_symbol
            best = min(best, self._minimax(board, True, agent_symbol, user_symbol))
            board[idx] = _EMPTY
        return best


_tic_tac_toe_service_singleton: TicTacToeService | None = None


def get_tic_tac_toe_service() -> TicTacToeService:
    global _tic_tac_toe_service_singleton
    if _tic_tac_toe_service_singleton is None:
        _tic_tac_toe_service_singleton = TicTacToeService()
    return _tic_tac_toe_service_singleton
