import os
import re
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.services.telemetry import track

logger = logging.getLogger("netracare.skills_loader")

# Path to the project-level skills/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"


class SkillMetadata:
    def __init__(self, name: str, description: str, folder_path: Path):
        self.name = name.strip()
        self.description = description.strip()
        self.folder_path = folder_path.resolve()

    def __repr__(self):
        return f"<SkillMetadata name='{self.name}'>"


class SkillsLoader:
    _instance: Optional["SkillsLoader"] = None

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = (skills_dir or DEFAULT_SKILLS_DIR).resolve()
        self.skills: Dict[str, SkillMetadata] = {}
        self._load_metadata()

    @classmethod
    def get_instance(cls, skills_dir: Optional[Path] = None) -> "SkillsLoader":
        if cls._instance is None:
            cls._instance = cls(skills_dir)
        return cls._instance

    def _load_metadata(self) -> None:
        """Scan skills directory and parse ONLY YAML front matter from each SKILL.md."""
        self.skills.clear()
        if not self.skills_dir.exists() or not self.skills_dir.is_dir():
            logger.warning(f"Skills directory not found at: {self.skills_dir}")
            return

        for entry in self.skills_dir.iterdir():
            if not entry.is_dir():
                continue
            skill_file = entry / "SKILL.md"
            if not skill_file.exists() or not skill_file.is_file():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                # Parse YAML front matter between first two '---' markers
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        yaml_text = parts[1]
                        data = yaml.safe_load(yaml_text) or {}
                        name = data.get("name", entry.name).strip()
                        description = data.get("description", "").strip()
                        self.skills[name] = SkillMetadata(
                            name=name,
                            description=description,
                            folder_path=entry
                        )
                        logger.info(f"Loaded skill metadata: '{name}' from {entry.name}")
            except Exception as e:
                logger.error(f"Failed to parse front matter for skill in {entry}: {e}")

    def get_available_skills_prompt(self) -> str:
        """Generate a short system prompt section listing only skill names and descriptions."""
        if not self.skills:
            return ""

        lines = ["AVAILABLE AGENT SKILLS:"]
        for name, meta in sorted(self.skills.items()):
            lines.append(f"- `{name}`: {meta.description}")
        lines.append(
            "\nTo use a skill, call `load_skill(name)`. "
            "If the skill instructions refer to an additional guide or checklist file, call `read_skill_file(name, file)`. "
            "Never guess or invent instructions outside the loaded skill."
        )
        return "\n".join(lines)

    @track(name="load_skill", tags=["skills", "load"])
    def load_skill(self, name: str) -> str:
        """
        Return the body of SKILL.md for the requested skill.
        Refuses unknown skills.
        """
        clean_name = (name or "").strip()
        if clean_name not in self.skills:
            available = ", ".join(sorted(self.skills.keys()))
            return f"Error: Unknown skill '{clean_name}'. Available skills: {available}."

        meta = self.skills[clean_name]
        skill_file = meta.folder_path / "SKILL.md"
        try:
            content = skill_file.read_text(encoding="utf-8")
            # Strip YAML front matter if present
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()
                    return body
            return content.strip()
        except Exception as e:
            logger.error(f"Error loading skill file {skill_file}: {e}")
            return f"Error: Could not load skill '{clean_name}'."

    @track(name="read_skill_file", tags=["skills", "read_file"])
    def read_skill_file(self, name: str, file: str) -> str:
        """
        Read a supporting document inside the specified skill folder.
        Rejects unknown skills and any path traversal outside the skill directory.
        """
        clean_name = (name or "").strip()
        if clean_name not in self.skills:
            available = ", ".join(sorted(self.skills.keys()))
            return f"Error: Unknown skill '{clean_name}'. Available skills: {available}."

        meta = self.skills[clean_name]
        skill_dir = meta.folder_path.resolve()

        clean_file = (file or "").strip()
        if not clean_file:
            return "Error: File name cannot be empty."

        # Security check: prevent directory traversal
        target_path = (skill_dir / clean_file).resolve()
        try:
            # Ensure target_path is relative to skill_dir (strictly within skill_dir)
            target_path.relative_to(skill_dir)
        except ValueError:
            logger.warning(f"Security: Path traversal attempt blocked: {clean_file} in skill {clean_name}")
            return "Error: Invalid file path or access outside skill directory."

        if not target_path.exists() or not target_path.is_file():
            return f"Error: File '{clean_file}' not found in skill '{clean_name}'."

        try:
            return target_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Error reading file {target_path}: {e}")
            return f"Error: Failed to read file '{clean_file}'."
