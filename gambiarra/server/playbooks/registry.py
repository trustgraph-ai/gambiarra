"""
Playbook registry - loads and manages playbook definitions.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PlaybookVariable:
    """Variable definition for a playbook."""
    name: str
    description: str
    required: bool = False
    default: Optional[str] = None


@dataclass
class PlaybookStep:
    """Single step in a playbook."""
    command: str
    timeout: int
    description: str
    working_dir: str = "."


@dataclass
class PlaybookDefinition:
    """Complete playbook definition."""
    name: str
    description: str
    tags: List[str]
    category: str
    steps: List[PlaybookStep]
    variables: List[PlaybookVariable] = field(default_factory=list)
    post_conditions: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""


class PlaybookRegistry:
    """Registry for managing playbooks."""

    def __init__(self, definitions_dir: Optional[Path] = None):
        """Initialize registry."""
        if definitions_dir is None:
            # Default to definitions directory in same package
            definitions_dir = Path(__file__).parent / "definitions"

        self.definitions_dir = Path(definitions_dir)
        self.playbooks: Dict[str, PlaybookDefinition] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all playbook definitions from YAML files."""
        if not self.definitions_dir.exists():
            logger.warning(f"Playbook definitions directory not found: {self.definitions_dir}")
            return

        for yaml_file in self.definitions_dir.glob("*.yaml"):
            try:
                playbook = self._load_playbook(yaml_file)
                self.playbooks[playbook.name] = playbook
                logger.info(f"📋 Loaded playbook: {playbook.name}")
            except Exception as e:
                logger.error(f"❌ Failed to load playbook {yaml_file.name}: {e}")

        logger.info(f"📚 Loaded {len(self.playbooks)} playbooks")

    def _load_playbook(self, yaml_file: Path) -> PlaybookDefinition:
        """Load a single playbook from YAML file."""
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)

        # Parse variables
        variables = []
        for var_data in data.get('variables', []):
            variables.append(PlaybookVariable(
                name=var_data['name'],
                description=var_data['description'],
                required=var_data.get('required', False),
                default=var_data.get('default')
            ))

        # Parse steps
        steps = []
        for step_data in data['steps']:
            steps.append(PlaybookStep(
                command=step_data['command'],
                timeout=step_data['timeout'],
                description=step_data['description'],
                working_dir=step_data.get('working_dir', '.')
            ))

        return PlaybookDefinition(
            name=data['name'],
            description=data['description'],
            tags=data.get('tags', []),
            category=data.get('category', 'general'),
            steps=steps,
            variables=variables,
            post_conditions=data.get('post_conditions', []),
            notes=data.get('notes', '')
        )

    def get_playbook(self, name: str) -> Optional[PlaybookDefinition]:
        """Get playbook by name."""
        return self.playbooks.get(name)

    def search_by_tags(self, tags: List[str]) -> List[PlaybookDefinition]:
        """Search playbooks by tags."""
        matches = []
        tags_lower = [t.lower() for t in tags]

        for playbook in self.playbooks.values():
            playbook_tags_lower = [t.lower() for t in playbook.tags]
            if any(tag in playbook_tags_lower for tag in tags_lower):
                matches.append(playbook)

        return matches

    def search_by_keywords(self, query: str) -> List[PlaybookDefinition]:
        """Search playbooks by keywords in name/description."""
        query_lower = query.lower()
        # Split query into individual keywords, filter out common words
        stop_words = {'a', 'an', 'the', 'with', 'for', 'to', 'of', 'in', 'on', 'at'}
        keywords = [w for w in query_lower.split() if w not in stop_words and len(w) > 2]

        matches = []

        for playbook in self.playbooks.values():
            # Check name, description, and tags
            searchable = f"{playbook.name} {playbook.description} {' '.join(playbook.tags)}".lower()

            # Count how many keywords match
            matches_count = sum(1 for keyword in keywords if keyword in searchable)

            # If at least half the keywords match, include it
            if matches_count >= len(keywords) / 2:
                matches.append(playbook)

        return matches

    def list_all(self) -> List[PlaybookDefinition]:
        """Get all playbooks."""
        return list(self.playbooks.values())

    def list_by_category(self, category: str) -> List[PlaybookDefinition]:
        """Get playbooks in a category."""
        return [p for p in self.playbooks.values() if p.category == category]


# Global registry instance
_registry: Optional[PlaybookRegistry] = None


def get_playbook_registry() -> PlaybookRegistry:
    """Get the global playbook registry."""
    global _registry
    if _registry is None:
        _registry = PlaybookRegistry()
    return _registry
