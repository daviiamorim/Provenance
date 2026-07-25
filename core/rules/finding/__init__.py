"""Register all Finding rules with RULE_REGISTRY at import time."""

from core.rules._registry import RULE_REGISTRY
from core.rules.finding._category_balance import CategoryBalanceRule
from core.rules.finding._distribution_shape import DistributionShapeRule
from core.rules.finding._duplicate_rate import DuplicateRateRule
from core.rules.finding._missing_rate import MissingRateRule
from core.rules.finding._variable_association import VariableAssociationRule

RULE_REGISTRY.register_finding(DistributionShapeRule())
RULE_REGISTRY.register_finding(MissingRateRule())
RULE_REGISTRY.register_finding(CategoryBalanceRule())
RULE_REGISTRY.register_finding(DuplicateRateRule())
RULE_REGISTRY.register_finding(VariableAssociationRule())
