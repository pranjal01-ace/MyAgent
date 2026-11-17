import os
import pytest
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from desktop.renderer_3d import Model3DRenderer
from desktop.character_renderer import CharacterRenderer, Sprite2DRenderer

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_phase3_facial_expressions(qapp):
    renderer = Model3DRenderer()
    renderer.load(Path("characters/ace_3d"))

    assert renderer.current_expression == "NEUTRAL"

    expressions = ["HAPPY", "SMILE", "LAUGH", "THINKING", "SURPRISED", "EXCITED", "CONFUSED", "WINK", "NEUTRAL"]
    for expr in expressions:
        renderer.set_expression(expr)
        assert renderer.current_expression == expr

def test_phase3_gaze_bounds_and_clamping(qapp):
    renderer = Model3DRenderer()
    renderer.load(Path("characters/ace_3d"))

    # Within normal range
    renderer.set_gaze(0.3, -0.4)
    assert renderer.current_gaze == (pytest.approx(0.3), pytest.approx(-0.4))

    # Overflows should be clamped strictly to [-1.0, 1.0]
    renderer.set_gaze(5.0, -10.0)
    assert renderer.current_gaze == (1.0, -1.0)

    renderer.set_gaze(-2.5, 3.2)
    assert renderer.current_gaze == (-1.0, 1.0)

def test_phase3_state_to_expression_mapping(qapp):
    renderer = Model3DRenderer()
    renderer.load(Path("characters/ace_3d"))

    # State transitions trigger their natural baseline expression
    renderer.set_state("HAPPY")
    assert renderer.current_state == "HAPPY"
    assert renderer.current_expression == "HAPPY"

    renderer.set_state("SPEAKING")
    assert renderer.current_state == "SPEAKING"
    assert renderer.current_expression == "SMILE"

    renderer.set_state("THINKING")
    assert renderer.current_state == "THINKING"
    assert renderer.current_expression == "THINKING"

    renderer.set_state("CONFUSED")
    assert renderer.current_state == "CONFUSED"
    assert renderer.current_expression == "CONFUSED"

    renderer.set_state("IDLE")
    assert renderer.current_state == "IDLE"
    assert renderer.current_expression == "NEUTRAL"

def test_phase3_blink_trigger(qapp):
    renderer = Model3DRenderer()
    renderer.load(Path("characters/ace_3d"))

    # Verify blink triggering executes safely
    renderer.trigger_blink("NORMAL")
    renderer.trigger_blink("DOUBLE")
    renderer.trigger_blink("LONG")

def test_phase3_character_renderer_base_contract(qapp):
    # Verify base CharacterRenderer and 2D sprite fallback support Phase 3 methods gracefully
    sprite_renderer = Sprite2DRenderer()
    sprite_renderer.set_expression("HAPPY")
    sprite_renderer.set_gaze(0.5, 0.5)
    sprite_renderer.trigger_blink("NORMAL")
