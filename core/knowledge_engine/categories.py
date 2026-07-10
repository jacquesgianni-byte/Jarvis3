"""
Knowledge Engine — Category Loader

Loads category definitions from data/categories.json.
The engine never hardcodes categories — all definitions are configuration.

New categories can be added by editing categories.json without any code changes.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_CATEGORIES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "categories.json"
)


@dataclass(frozen=True)
class CategoryDefinition:
    """
    A single category definition loaded from configuration.

    Attributes:
        id:                  Unique category identifier. Used as the category
                             value on MemoryRecord.
        label:               Human-readable display name.
        description:         What this category is for.
        default_importance:  Default importance applied to memories in this
                             category when none is explicitly provided.
        default_visibility:  Default visibility applied to memories in this
                             category when none is explicitly provided.
    """

    id: str
    label: str
    description: str
    default_importance: float
    default_visibility: str


class CategoryLoader:
    """
    Loads and provides access to category definitions from categories.json.

    Categories are loaded once at construction time and cached in memory.
    If the configuration file cannot be loaded, a minimal fallback set
    is used so the engine can continue operating.

    Example usage:
        loader = CategoryLoader()
        category = loader.get("preferences")
        print(category.default_importance)  # 0.6
    """

    def __init__(self, path: Optional[str] = None):
        """
        Initialise the CategoryLoader.

        Args:
            path: Optional path to categories.json.
                  Defaults to data/categories.json relative to the project root.
        """
        self._path = path or _DEFAULT_CATEGORIES_PATH
        self._categories: dict[str, CategoryDefinition] = {}
        self._load()

    def _load(self) -> None:
        """
        Load category definitions from the configuration file.

        Falls back to a minimal set if the file cannot be read.
        """
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            for entry in raw:
                definition = CategoryDefinition(
                    id=entry["id"],
                    label=entry["label"],
                    description=entry.get("description", ""),
                    default_importance=entry.get("default_importance", 0.5),
                    default_visibility=entry.get("default_visibility", "private"),
                )
                self._categories[definition.id] = definition

            logger.info(
                "CategoryLoader: loaded %d categories from %s",
                len(self._categories),
                self._path
            )

        except FileNotFoundError:
            logger.warning(
                "CategoryLoader: categories.json not found at %s. "
                "Using fallback category.",
                self._path
            )
            self._load_fallback()

        except Exception:
            logger.exception(
                "CategoryLoader: failed to load categories.json. "
                "Using fallback category."
            )
            self._load_fallback()

    def _load_fallback(self) -> None:
        """Load a minimal fallback category set so the engine remains functional."""
        fallback = CategoryDefinition(
            id="general",
            label="General",
            description="Catch-all for uncategorised facts.",
            default_importance=0.4,
            default_visibility="private",
        )
        self._categories = {"general": fallback}

    def get(self, category_id: str) -> Optional[CategoryDefinition]:
        """
        Return the CategoryDefinition for the given id.

        Args:
            category_id: The category id to look up.

        Returns:
            The CategoryDefinition, or None if not found.
        """
        return self._categories.get(category_id)

    def get_or_general(self, category_id: str) -> CategoryDefinition:
        """
        Return the CategoryDefinition for the given id, falling back to general.

        Args:
            category_id: The category id to look up.

        Returns:
            The matching CategoryDefinition, or the general category.
        """
        return self._categories.get(category_id) or self._categories["general"]

    def all(self) -> list[CategoryDefinition]:
        """
        Return all loaded category definitions.

        Returns:
            A list of all CategoryDefinition objects.
        """
        return list(self._categories.values())

    def is_valid(self, category_id: str) -> bool:
        """
        Return True if the given category id is defined in configuration.

        Args:
            category_id: The category id to check.

        Returns:
            True if the category exists.
        """
        return category_id in self._categories