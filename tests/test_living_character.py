import os
import pytest
from PyQt5.QtWidgets import QApplication
from desktop.living_character import NativeLivingCharacter, LivingCharacterWidget
from desktop.character_renderer import LivingCharacterRenderer, Sprite2DRenderer

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_native_living_character_states(qapp):
    char = NativeLivingCharacter()
    
    # Initial state
    assert char.current_state == "IDLE"
    assert char.mouth_openness == 0.0
    
    # State transition to SPEAKING
    char.set_state("SPEAKING")
    assert char.current_state == "SPEAKING"
    
    # Simulate animation ticks
    for _ in range(10):
        char._on_anim_frame()
        
    assert char.mouth_openness > 0.0 # Mouth speaking lip-sync active
    assert char.left_arm_angle != 0.0 or char.right_arm_angle != 0.0 # Living hand gesture active
    
    # State transition to THINKING
    char.set_state("THINKING")
    assert char.current_state == "THINKING"
    char._on_anim_frame()
    assert char.right_arm_angle == pytest.approx(-1.15) # Chin rest pose

def test_living_character_widget(qapp):
    widget = LivingCharacterWidget(use_web=False)
    widget.set_state("SPEAKING")
    assert widget.engine.current_state == "SPEAKING"

def test_sprite2d_renderer_overlay(qapp):
    from pathlib import Path
    renderer = Sprite2DRenderer()
    char_path = Path("characters/ace")
    if char_path.exists():
        renderer.load(char_path)
        renderer.set_state("SPEAKING")
        assert renderer.current_state in ["SPEAKING", "TALKING"]

def test_living_character_renderer(qapp):
    renderer = LivingCharacterRenderer()
    renderer.set_state("SPEAKING")
    assert renderer.widget.engine.current_state == "SPEAKING"

