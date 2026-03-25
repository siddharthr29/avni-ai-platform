"""Avni AI Platform -- service layer.

Public exports for the most commonly used services. Individual modules
can still be imported directly (e.g. ``from app.services.bundle_generator
import generate_from_srs``).
"""

from app.services.bundle_regenerator import BundleRegenerator
from app.services.clarity_engine import ClarityEngine, clarity_engine
from app.services.preflight_validator import PreFlightValidator
from app.services.provider_chain import ProviderChain, ProviderResult, provider_chain
from app.services.workflow_engine import WorkflowEngine, workflow_engine

__all__ = [
    # Provider chain
    "provider_chain",
    "ProviderChain",
    "ProviderResult",
    # Workflow engine
    "workflow_engine",
    "WorkflowEngine",
    # Validation
    "PreFlightValidator",
    # Clarity engine
    "clarity_engine",
    "ClarityEngine",
    # Bundle regeneration
    "BundleRegenerator",
]
