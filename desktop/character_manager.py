import os
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("desktop.character_manager")

CHARACTERS_ROOT = Path(__file__).resolve().parent.parent / "characters"
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
ACTIVE_CHAR_FILE = CONFIG_DIR / "active_character.json"

DEFAULT_CHARACTER_ID = "ace"

class CharacterManager:
    """Manages character loading, discovery, importing, validation, and active selection."""

    def __init__(self):
        CHARACTERS_ROOT.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.active_character_id = self._load_active_character_id()

    def _load_active_character_id(self) -> str:
        if ACTIVE_CHAR_FILE.exists():
            try:
                with open(ACTIVE_CHAR_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("active_character", DEFAULT_CHARACTER_ID)
            except Exception as e:
                logger.warning(f"Could not read active_character.json: {e}")
        return DEFAULT_CHARACTER_ID

    def set_active_character(self, character_id: str) -> bool:
        char_dir = CHARACTERS_ROOT / character_id
        if not char_dir.exists():
            logger.error(f"Character '{character_id}' does not exist in {CHARACTERS_ROOT}")
            return False

        self.active_character_id = character_id
        try:
            with open(ACTIVE_CHAR_FILE, "w", encoding="utf-8") as f:
                json.dump({"active_character": character_id}, f, indent=4)
            logger.info(f"Active character set to: {character_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save active character: {e}")
            return False

    def get_active_character_path(self) -> Path:
        char_path = CHARACTERS_ROOT / self.active_character_id
        if not char_path.exists():
            # Fallback to ace or first available
            available = self.list_available_characters()
            if available:
                return available[0]["path"]
            return CHARACTERS_ROOT / DEFAULT_CHARACTER_ID
        return char_path

    def get_active_manifest(self) -> dict:
        path = self.get_active_character_path()
        manifest_file = path / "character.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading active manifest: {e}")
        return {
            "id": self.active_character_id,
            "name": self.active_character_id.title(),
            "personality": {}
        }

    def list_available_characters(self) -> List[dict]:
        """Scan characters/ directory and return list of character metadata cards."""
        characters = []
        if not CHARACTERS_ROOT.exists():
            return characters

        for folder in CHARACTERS_ROOT.iterdir():
            if folder.is_dir():
                manifest_file = folder / "character.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            data["path"] = folder
                            characters.append(data)
                    except Exception as e:
                        logger.warning(f"Invalid manifest in {folder.name}: {e}")
        return characters

    def validate_character_folder(self, folder_path: Path) -> Tuple[bool, List[str], Optional[dict]]:
        """Validate an imported character directory."""
        folder_path = Path(folder_path)
        issues = []
        
        if not folder_path.exists() or not folder_path.is_dir():
            return False, ["Folder does not exist or is not a directory."], None

        manifest_file = folder_path / "character.json"
        if not manifest_file.exists():
            return False, ["Missing 'character.json' manifest file in folder."], None

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            return False, [f"JSON Syntax error in character.json: {e}"], None

        req_fields = ["id", "name"]
        for field in req_fields:
            if field not in manifest:
                issues.append(f"Manifest missing required field '{field}'.")

        assets = manifest.get("assets", {})
        if "idle" not in assets:
            issues.append("Warning: 'idle' asset missing in manifest; will fallback to idle.png.")
        else:
            idle_file = folder_path / assets["idle"]
            if not idle_file.exists():
                issues.append(f"Warning: Referenced idle asset '{assets['idle']}' file not found.")

        is_valid = len([i for i in issues if not i.startswith("Warning:")]) == 0
        return is_valid, issues, manifest

    def import_character_folder(self, folder_path: Path) -> Tuple[bool, str]:
        """Import a user character folder into characters/ directory."""
        is_valid, issues, manifest = self.validate_character_folder(folder_path)
        if not is_valid:
            return False, "\n".join(issues)

        char_id = manifest.get("id", folder_path.name.lower().replace(" ", "_"))
        target_dir = CHARACTERS_ROOT / char_id

        try:
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(folder_path, target_dir)
            self.set_active_character(char_id)
            return True, f"Successfully imported character '{manifest.get('name')}'!"
        except Exception as e:
            return False, f"Failed to import character folder: {e}"

    def get_character_system_prompt(self) -> str:
        """Generate Ollama system prompt based on active character and personality.json."""
        manifest = self.get_active_manifest()
        name = manifest.get("name", "AI Companion")
        p = manifest.get("personality", {})
        
        # Check if config/personality.json overrides
        pers_file = CONFIG_DIR / "personality.json"
        if pers_file.exists():
            try:
                with open(pers_file, "r", encoding="utf-8") as f:
                    custom_p = json.load(f)
                    if custom_p.get("name"):
                        name = custom_p["name"]
                    p.update(custom_p)
            except Exception as e:
                logger.warning(f"Error reading personality.json: {e}")

        traits = p.get("personality", "helpful, friendly, clear")
        if isinstance(traits, list):
            traits = ", ".join(traits)
        style = p.get("speech_style", "casual, direct, friendly")
        humor = "Use light humor when appropriate." if p.get("humor", True) else "Be direct and helpful."
        verbosity = p.get("verbosity", "medium")

        char_id = manifest.get("id", "").lower()
        is_ace = "ace" in char_id or "ace" in name.lower()

        if is_ace:
            prompt = (
                f"You are Portgas D. Ace, acting as the user's companion and assistant.\n\n"
                f"Core Personality & Vibe:\n"
                f"- You combine warmth, natural confidence, easygoing charm, pride, and a deep sense of responsibility (like a dependable older brother).\n"
                f"- You are grounded and natural. You don't brag or yell; you know what you're capable of.\n"
                f"- Your exterior is relaxed, comfortable, and slightly amused, but you take the user's goals and well-being seriously.\n\n"
                f"Conversational Style & Mannerisms:\n"
                f"- Sentence length: Short to medium. Conversational and punchy, not long monologues.\n"
                f"- Vocabulary: Casual and direct ('Yeah', 'Huh?', 'What?', 'Come on', 'Really?', 'Don\\'t worry about it', 'I\\'m fine', 'You okay?', 'Let\\'s go', 'Heh').\n"
                f"- Formula: Casual observation -> short response -> little tease or grin -> direct helpful action.\n"
                f"- Confidence: Natural and instinctive ('You need this fixed? Fine, let\\'s do it.') rather than arrogant ('I\\'m the greatest!').\n"
                f"- Emotional weight: Understated. You show loyalty through direct help and actions rather than emotional speeches.\n\n"
                f"Assisting with Tasks & Code:\n"
                f"- When helping with coding, technical questions, or tasks, be sharp, practical, and clear.\n"
                f"- Provide clean code and concise explanations while maintaining your relaxed, confident brotherly attitude.\n\n"
                f"Strict Rules (DO NOT BREAK):\n"
                f"1. Never bring up or relate topics to One Piece, pirates, anime lore, or Devil Fruits unless the user explicitly asks about them. For all standard topics (coding, studying, tasks, daily life), stay strictly grounded in the real world. If and only if the user explicitly asks about One Piece, discuss it naturally and knowledgeably.\n"
                f"2. NEVER use cartoonish shouting or childish hype (NEVER say 'WOOHOO!', 'yeehaw', 'buddy', 'all ears', 'all eyes').\n"
                f"3. NEVER shout or force attack/technique names (DO NOT scream 'Fire Fist!', 'Hiken!', etc.).\n"
                f"4. NEVER use stereotypical pirate clichés ('ahoy', 'matey', 'shiver me timbers', 'shipshape').\n"
                f"5. If context from the knowledge base is provided, use it accurately.\n"
                f"6. Never claim to have executed desktop tools unless the tool was genuinely run."
            )
        else:
            prompt = (
                f"You are {name}, an AI companion and assistant.\n"
                f"Personality Traits: {traits}\n"
                f"Speech Style: {style}\n"
                f"{humor}\n"
                f"Verbosity: {verbosity}\n"
                f"- Speak naturally, clearly, and helpfully.\n"
                f"- If context from the knowledge base is provided, use it accurately.\n"
                f"- Never claim to execute desktop tools unless the tool system actually ran them."
            )
        return prompt


