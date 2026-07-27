"""Catalog endpoint — declares what each registered plugin can produce."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import CapabilityOut, CatalogOut
from plugins.tabular import TabularPlugin

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[CatalogOut])
def get_catalog() -> list[CatalogOut]:
    """Return the full capability catalog for all registered plugins."""
    plugins = [TabularPlugin()]
    result: list[CatalogOut] = []
    for plugin in plugins:
        cat = plugin.catalog()
        result.append(
            CatalogOut(
                plugin_name=plugin.name,
                capabilities=[
                    CapabilityOut(
                        id=c.id,
                        description=c.description,
                        params_schema=c.params_schema,
                        produces=list(c.produces),
                        renders=c.renders,
                        cost=c.cost,
                    )
                    for c in cat.capabilities
                ],
                measurement_types=list(cat.measurement_types),
            )
        )
    return result
