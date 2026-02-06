"""
Traits library loader and manager.

Loads trait definitions from config/personas/traits.yaml
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional

from .models import PersonaTrait, TraitCategory


class TraitsLibrary:
    """
    Manages personality traits loaded from configuration.

    Traits define behavioral parameters that influence
    how SimulatedClient responds.
    """

    _instance: Optional["TraitsLibrary"] = None
    _config_path: Path = Path("config/personas/traits.yaml")
    _traits: Dict[str, PersonaTrait] = {}
    _loaded: bool = False

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize traits library.

        Args:
            config_path: Path to traits.yaml (default: config/personas/traits.yaml)
        """
        if config_path:
            TraitsLibrary._config_path = config_path
        if not TraitsLibrary._loaded:
            self._load_traits()

    def _load_traits(self) -> None:
        """Load traits from YAML configuration."""
        if not self._config_path.exists():
            # Create default config if not exists
            self._create_default_config()

        with open(self._config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        traits_data = config.get('traits', {})

        for trait_id, trait_data in traits_data.items():
            try:
                self._traits[trait_id] = PersonaTrait(
                    id=trait_id,
                    category=TraitCategory(trait_data.get('category', 'emotional')),
                    response_length=trait_data.get('response_length', 1.0),
                    detail_level=trait_data.get('detail_level', 1.0),
                    formality=trait_data.get('formality', 1.0),
                    objection_prob=trait_data.get('objection_prob', 0.2),
                    question_prob=trait_data.get('question_prob', 0.3),
                    interrupt_prob=trait_data.get('interrupt_prob', 0.1),
                    hesitation_prob=trait_data.get('hesitation_prob', 0.1),
                    focuses_on=trait_data.get('focuses_on', []),
                    avoids_topics=trait_data.get('avoids_topics', []),
                )
            except Exception:
                # Skip invalid traits
                continue

        self._loaded = True

    def _create_default_config(self) -> None:
        """Create default traits configuration file."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        default_config = {
            'meta': {
                'version': '1.0',
                'description': 'Personality traits library for simulated clients'
            },
            'traits': {
                # Communication traits
                'brief': {
                    'category': 'communication',
                    'response_length': 0.5,
                    'detail_level': 0.3,
                },
                'verbose': {
                    'category': 'communication',
                    'response_length': 1.8,
                    'detail_level': 1.5,
                },
                'formal': {
                    'category': 'communication',
                    'formality': 1.5,
                },
                'casual': {
                    'category': 'communication',
                    'formality': 0.5,
                },
                # Decision traits
                'decisive': {
                    'category': 'decision',
                    'hesitation_prob': 0.05,
                },
                'indecisive': {
                    'category': 'decision',
                    'hesitation_prob': 0.6,
                    'question_prob': 0.5,
                },
                'skeptic': {
                    'category': 'decision',
                    'objection_prob': 0.6,
                    'question_prob': 0.4,
                    'focuses_on': ['guarantee', 'proof', 'cases'],
                },
                'impulsive': {
                    'category': 'decision',
                    'interrupt_prob': 0.3,
                    'hesitation_prob': 0.02,
                },
                # Knowledge traits
                'expert': {
                    'category': 'knowledge',
                    'detail_level': 1.3,
                    'question_prob': 0.5,
                    'focuses_on': ['technical', 'integration', 'api'],
                },
                'novice': {
                    'category': 'knowledge',
                    'question_prob': 0.4,
                    'avoids_topics': ['technical'],
                },
                # Emotional traits
                'busy': {
                    'category': 'emotional',
                    'response_length': 0.6,
                    'interrupt_prob': 0.4,
                },
                'frustrated': {
                    'category': 'emotional',
                    'objection_prob': 0.5,
                    'formality': 0.7,
                },
                'enthusiastic': {
                    'category': 'emotional',
                    'response_length': 1.3,
                    'objection_prob': 0.05,
                },
                'price_sensitive': {
                    'category': 'emotional',
                    'objection_prob': 0.4,
                    'focuses_on': ['price', 'cost', 'budget', 'roi'],
                },
            }
        }

        with open(self._config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)

    def get(self, trait_id: str) -> Optional[PersonaTrait]:
        """
        Get trait by ID.

        Args:
            trait_id: Trait identifier

        Returns:
            PersonaTrait or None if not found
        """
        return self._traits.get(trait_id)

    def get_many(self, trait_ids: List[str]) -> List[PersonaTrait]:
        """
        Get multiple traits by IDs.

        Args:
            trait_ids: List of trait identifiers

        Returns:
            List of found PersonaTraits (skips missing)
        """
        return [t for tid in trait_ids if (t := self.get(tid))]

    def list_all(self) -> List[str]:
        """Get all available trait IDs."""
        return list(self._traits.keys())

    def list_by_category(self, category: TraitCategory) -> List[str]:
        """
        Get trait IDs by category.

        Args:
            category: TraitCategory to filter by

        Returns:
            List of trait IDs in that category
        """
        return [
            tid for tid, trait in self._traits.items()
            if trait.category == category
        ]

    def reload(self) -> None:
        """Force reload traits from configuration."""
        self._loaded = False
        self._traits.clear()
        self._load_traits()


# Singleton instance
_library: Optional[TraitsLibrary] = None


def get_traits_library(config_path: Optional[Path] = None) -> TraitsLibrary:
    """
    Get or create traits library singleton.

    Args:
        config_path: Optional path to traits.yaml

    Returns:
        TraitsLibrary instance
    """
    global _library
    if _library is None or config_path is not None:
        _library = TraitsLibrary(config_path)
    return _library
