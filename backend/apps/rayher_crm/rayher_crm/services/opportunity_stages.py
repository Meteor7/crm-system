"""Opportunity stage and probability-level vocabulary shared by services, patches and tests."""

from __future__ import annotations

# Ordered from lowest to highest. An empty level means the owner has not set one yet.
PROBABILITY_LEVELS = ("low_probability", "pipeline", "upside", "committed")
PROBABILITY_LEVEL_CHOICES = {"", *PROBABILITY_LEVELS}

QUALIFIED_OPPORTUNITY = "qualified_opportunity"
DEMO_DONE = "demo_done"
CUSTOMER_BUDGET_APPROVED = "customer_budget_approved"
RFQ_VALIDATED = "rfq_validated"
QUOTATION_SENT = "quotation_sent"
INTERNAL_VALIDATION = "internal_validation"
PO_RECEIVED = "po_received"
LOST = "lost"

# Stages are milestones already reached, in order. Internal validation (S6) is optional.
MILESTONE_STAGES = (
    QUALIFIED_OPPORTUNITY,
    DEMO_DONE,
    CUSTOMER_BUDGET_APPROVED,
    RFQ_VALIDATED,
    QUOTATION_SENT,
    INTERNAL_VALIDATION,
    PO_RECEIVED,
)
OPPORTUNITY_STAGES = (*MILESTONE_STAGES, LOST)
# S1-S6 are still being worked; they are also the only stages an Opportunity can be lost at.
OPEN_STAGES = MILESTONE_STAGES[:-1]
CLOSED_STAGES = (PO_RECEIVED, LOST)
DEMO_REQUEST_STAGES = (QUALIFIED_OPPORTUNITY, DEMO_DONE)
PUBLISHABLE_QUOTATION_STAGES = (RFQ_VALIDATED, QUOTATION_SENT, INTERNAL_VALIDATION)
PO_CONFIRMABLE_STAGES = (QUOTATION_SENT, INTERNAL_VALIDATION)

STAGE_HISTORY_SOURCES = ("creation", "event", "manual", "approval", "rollback", "lost", "migration")
STAGE_HISTORY_EVENTS = (
    "created",
    "lead_converted",
    "demo_customer_review",
    "budget_confirmed",
    "rfq_approved",
    "quotation_published",
    "internal_validation_approved",
    "po_confirmed",
    "marked_lost",
    "rollback",
    "reopened",
    "migration",
)
REACHED_AT_BASES = ("recorded", "declared", "evidence", "upper_bound", "unknown")
INTERNAL_VALIDATION_STATUSES = ("pending", "approved", "rejected", "cancelled")

# Server workflow events that move an Opportunity forward: event -> (required stage, target stage).
AUTOMATIC_STAGE_EVENTS = {
    "demo_customer_review": (QUALIFIED_OPPORTUNITY, DEMO_DONE),
    "rfq_approved": (CUSTOMER_BUDGET_APPROVED, RFQ_VALIDATED),
    "quotation_published": (RFQ_VALIDATED, QUOTATION_SENT),
}


def stage_index(stage: str) -> int:
    """Position of a milestone stage; Lost has no position in the funnel."""

    return MILESTONE_STAGES.index(stage)
