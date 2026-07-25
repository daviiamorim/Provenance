"""Register all Assessment rules with RULE_REGISTRY at import time."""

from core.rules._registry import RULE_REGISTRY
from core.rules.assessment._data_quality import DataQualityRule
from core.rules.assessment._modeling_readiness import ModelingReadinessRule

RULE_REGISTRY.register_assessment(ModelingReadinessRule())
RULE_REGISTRY.register_assessment(DataQualityRule())
