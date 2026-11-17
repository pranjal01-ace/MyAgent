import os
import pytest
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from desktop.renderer_3d import Model3DRenderer

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_phase2_animation_state_transitions(qapp):
    renderer = Model3DRenderer()
    renderer.load(Path("characters/ace_3d"))

    # Test state transitions
    states = ["IDLE", "LISTENING", "THINKING", "SPEAKING", "HAPPY", "INTERRUPT"]
    for s in states:
        renderer.set_state(s)
        assert renderer.current_state == s
