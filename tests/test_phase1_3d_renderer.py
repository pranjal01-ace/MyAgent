import os
import pytest
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from desktop.character_manager import CharacterManager
from desktop.renderer_3d import Model3DRenderer

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_character_manager_3d_manifest(qapp):
    manager = CharacterManager()
    manifest = manager.get_active_manifest()
    assert manifest is not None
    assert "name" in manifest

def test_3d_model_file_exists():
    glb_path = Path("characters/ace_3d/model.glb")
    assert glb_path.exists(), "3D model.glb binary file should exist in characters/ace_3d/"
    assert glb_path.stat().st_size > 0, "model.glb must not be empty"

def test_model3d_renderer_init(qapp):
    renderer = Model3DRenderer()
    char_path = Path("characters/ace_3d")
    loaded = renderer.load(char_path)
    assert loaded is True
    
    renderer.set_state("SPEAKING")
    assert renderer.current_state == "SPEAKING"
    
    renderer.set_scale(1.2)
    assert renderer.scale_factor == 1.2
