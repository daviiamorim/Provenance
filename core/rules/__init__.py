"""core.rules — Finding and Assessment rule system.

Import this package to get RULE_REGISTRY pre-populated with all built-in
rules.  Rules are registered as side effects of importing the sub-packages.
"""

import core.rules.assessment as _assessment_rules  # noqa: F401
import core.rules.finding as _finding_rules  # noqa: F401
from core.rules._registry import RULE_REGISTRY, AssessmentRule, FindingRule

__all__ = ["RULE_REGISTRY", "AssessmentRule", "FindingRule"]
