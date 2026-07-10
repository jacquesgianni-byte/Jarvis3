"""
Rule loading for the Thought & Reasoning Engine (Genesis-013 Task 001).

Rules are DATA, never code. [R2] The loader's contract is a directory:
every valid *.json file in data/rules/ is loaded, so future rule packs
(sports.json, household.json, ...) drop in without any code change.

File schema:

    {
      "sets": {
        "afl_clubs": ["Brisbane Lions", "Carlton", "..."]
      },
      "rules": [
        {
          "id": "team_implies_sport",
          "if": [
            {"attribute": "favourite team", "in_set": "afl_clubs"}
          ],
          "then": {"attribute": "followed sport", "value": "AFL"},
          "confidence": 0.9
        }
      ]
    }

Premise kinds: exactly one of
    "equals": "<value>"     value must equal (case-insensitive)
    "in_set": "<set name>"  value must be in the named set
    "exists": true          any stored value satisfies

Validation follows the CategoryLoader precedent: invalid rules or files
are skipped with a WARNING and the engine starts with the valid subset.
Sets are merged across all files before rules are validated, so a rule
pack may reference sets defined in another pack.
"""

import json
import logging
from pathlib import Path

from core.reasoning.models import Premise, Rule

logger = logging.getLogger(__name__)

_DEFAULT_RULES_DIR = Path(__file__).resolve().parent / ".." / ".." / "data" / "rules"


class RuleLoader:
    """Loads and validates every rule file in a directory."""

    def __init__(self, rules_dir=None):
        self.rules_dir = Path(rules_dir) if rules_dir else _DEFAULT_RULES_DIR
        self.sets: dict = {}
        self.rules: list = []

    def load(self) -> list:
        """Load all rule packs. Returns the list of valid rules."""

        self.sets = {}
        self.rules = []

        directory = self.rules_dir.resolve()
        if not directory.is_dir():
            logger.warning("RuleLoader: rules directory not found: %s", directory)
            return self.rules

        files = sorted(directory.glob("*.json"))
        parsed = []

        # Pass 1 — parse files and merge sets across all packs.
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError) as error:
                logger.warning(
                    "RuleLoader: skipping unreadable rule file %s (%s)",
                    path.name, error,
                )
                continue

            if not isinstance(data, dict):
                logger.warning(
                    "RuleLoader: skipping %s — top level must be an object.",
                    path.name,
                )
                continue

            sets = data.get("sets", {})
            if isinstance(sets, dict):
                for name, values in sets.items():
                    if isinstance(values, list):
                        self.sets[str(name)] = [str(v) for v in values]
                    else:
                        logger.warning(
                            "RuleLoader: set %r in %s is not a list — skipped.",
                            name, path.name,
                        )
            parsed.append((path.name, data))

        # Pass 2 — validate and build rules.
        seen_ids = set()
        for filename, data in parsed:
            raw_rules = data.get("rules", [])
            if not isinstance(raw_rules, list):
                logger.warning(
                    "RuleLoader: 'rules' in %s is not a list — skipped.", filename
                )
                continue

            for raw in raw_rules:
                rule = self._build_rule(raw, filename, seen_ids)
                if rule is not None:
                    self.rules.append(rule)
                    seen_ids.add(rule.id)

        logger.info(
            "RuleLoader: loaded %d rule(s) and %d set(s) from %d file(s) in %s",
            len(self.rules), len(self.sets), len(files), directory,
        )
        return self.rules

    # ------------------------------------------------------------------

    def _build_rule(self, raw, filename, seen_ids):
        """Validate one raw rule dict. Returns a Rule or None."""

        def reject(reason):
            logger.warning(
                "RuleLoader: skipping invalid rule in %s (%s): %r",
                filename, reason, raw,
            )
            return None

        if not isinstance(raw, dict):
            return reject("not an object")

        rule_id = raw.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            return reject("missing id")
        if rule_id in seen_ids:
            return reject("duplicate id")

        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)) or not (0.0 < confidence <= 1.0):
            return reject("confidence must be in (0, 1]")

        conclusion = raw.get("then")
        if (
            not isinstance(conclusion, dict)
            or not str(conclusion.get("attribute", "")).strip()
            or not str(conclusion.get("value", "")).strip()
        ):
            return reject("'then' needs attribute and value")

        raw_premises = raw.get("if")
        if not isinstance(raw_premises, list) or not raw_premises:
            return reject("'if' must be a non-empty list")

        premises = []
        for condition in raw_premises:
            premise = self._build_premise(condition)
            if premise is None:
                return reject(f"invalid premise: {condition!r}")
            premises.append(premise)

        return Rule(
            id=rule_id.strip(),
            premises=tuple(premises),
            conclusion_attribute=str(conclusion["attribute"]).strip().lower(),
            conclusion_value=str(conclusion["value"]).strip(),
            confidence=float(confidence),
            source_file=filename,
        )

    def _build_premise(self, condition):
        if not isinstance(condition, dict):
            return None

        attribute = str(condition.get("attribute", "")).strip().lower()
        if not attribute:
            return None

        kinds = [k for k in ("equals", "in_set", "exists") if k in condition]
        if len(kinds) != 1:
            return None
        kind = kinds[0]

        if kind == "equals":
            operand = str(condition["equals"]).strip()
            if not operand:
                return None
        elif kind == "in_set":
            operand = str(condition["in_set"]).strip()
            if operand not in self.sets:
                return None            # unknown set — rule rejected
        else:                          # exists
            if condition["exists"] is not True:
                return None
            operand = None

        return Premise(attribute=attribute, kind=kind, operand=operand)