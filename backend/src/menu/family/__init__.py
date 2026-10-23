"""Modulo family (strato 6): famiglia, persone, onboarding; registra il proprio export."""

from menu.common import register_export_contributor
from menu.family.access import family_access
from menu.family.export import FamilyExport
from menu.family.membership import FamilyBrief, Membership, context_for, membership_for
from menu.family.onboarding import FamilyOnboarding

register_export_contributor(FamilyExport())

__all__ = [
    "FamilyBrief",
    "FamilyOnboarding",
    "Membership",
    "context_for",
    "family_access",
    "membership_for",
]
