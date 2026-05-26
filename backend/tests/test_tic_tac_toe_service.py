from app.services.tic_tac_toe_service import TicTacToeService


def test_start_command_creates_active_game() -> None:
    service = TicTacToeService()

    result = service.process_message("/ttt start", None)

    assert result.context["tic_tac_toe"]["active"] is True
    assert result.context["tic_tac_toe"]["board"] == [" "] * 9
    assert "New Tic Tac Toe game started" in result.response


def test_move_without_active_game_returns_hint() -> None:
    service = TicTacToeService()

    result = service.process_message("/ttt 5", {})

    assert "No active game" in result.response


def test_number_message_is_handled_when_game_active() -> None:
    service = TicTacToeService()
    started = service.process_message("/ttt start", None)

    assert service.should_handle("5", started.context) is True

    moved = service.process_message("5", started.context)

    assert moved.context["tic_tac_toe"]["board"][4] == "X"
    assert "I played" in moved.response or "draw" in moved.response.lower() or "win" in moved.response.lower()


def test_rejects_occupied_cell() -> None:
    service = TicTacToeService()
    started = service.process_message("/ttt start", None)
    after_first_move = service.process_message("/ttt 1", started.context)

    second_try = service.process_message("/ttt 1", after_first_move.context)

    assert "already occupied" in second_try.response


def test_natural_language_start_request() -> None:
    service = TicTacToeService()

    assert service.should_handle("let's play tic tac toe", None) is True
    result = service.process_message("let's play tic tac toe", None)

    assert result.context["tic_tac_toe"]["active"] is True
