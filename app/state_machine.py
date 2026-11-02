"""State Machine & Customer Enquiry Memory for AI Master Carpenter Assistant.

Implements the 14-stage conversation state machine:
NEW_ENQUIRY -> GREETING -> REQUIREMENT_COLLECTION -> PROJECT_DISCOVERY ->
BUDGET_DISCUSSION -> ESTIMATION -> VISIT_REQUESTED -> VISIT_CONFIRMED ->
QUOTATION_PENDING -> QUOTATION_SENT -> NEGOTIATION -> FOLLOW_UP ->
JOB_WON / JOB_LOST -> HUMAN_HANDOVER.

Guarantees:
- Customer is never re-asked an already answered question.
- Customer can modify requirements at any point without restarting.
- Human handover mode suppresses AI auto-replies when human carpenter is active.
- Memory persists per customer with full auditability.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("carpenter.state_machine")


class ConversationStage(str, Enum):
    """The 14 distinct stages of customer conversation and lead progression."""
    NEW_ENQUIRY = "NEW_ENQUIRY"
    GREETING = "GREETING"
    REQUIREMENT_COLLECTION = "REQUIREMENT_COLLECTION"
    PROJECT_DISCOVERY = "PROJECT_DISCOVERY"
    BUDGET_DISCUSSION = "BUDGET_DISCUSSION"
    ESTIMATION = "ESTIMATION"
    VISIT_REQUESTED = "VISIT_REQUESTED"
    VISIT_CONFIRMED = "VISIT_CONFIRMED"
    QUOTATION_PENDING = "QUOTATION_PENDING"
    QUOTATION_SENT = "QUOTATION_SENT"
    NEGOTIATION = "NEGOTIATION"
    FOLLOW_UP = "FOLLOW_UP"
    JOB_WON = "JOB_WON"
    JOB_LOST = "JOB_LOST"
    HUMAN_HANDOVER = "HUMAN_HANDOVER"


# Priority of missing info collection
DISCOVERY_FIELDS_ORDER = [
    "furniture_type",
    "dimensions",
    "materials",
    "finish",
]


@dataclass
class CustomerEnquiryMemory:
    """Persistent structured enquiry memory per customer."""
    phone: str
    customer_name: Optional[str] = None
    stage: str = ConversationStage.NEW_ENQUIRY.value
    project_type: Optional[str] = None
    room_type: Optional[str] = None
    dimensions: Optional[str] = None
    preferred_materials: List[str] = field(default_factory=list)
    preferred_finish: Optional[str] = None
    hardware_preference: Optional[str] = None
    customer_budget: Optional[int] = None
    estimated_price: Optional[str] = None
    timeline: Optional[str] = None
    site_address: Optional[str] = None
    locality: Optional[str] = None
    visit_slot: Optional[str] = None
    consultation_mode: str = "in_person"
    human_handover: bool = False
    answered_fields: Set[str] = field(default_factory=set)
    notes: List[str] = field(default_factory=list)
    last_intent: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def mark_answered(self, field_name: str) -> None:
        """Mark a discovery question as answered so it is never re-asked."""
        self.answered_fields.add(field_name)
        if field_name in ("furniture_type", "project_type"):
            self.answered_fields.add("furniture_type")
            self.answered_fields.add("project_type")
        elif field_name in ("materials", "preferred_materials"):
            self.answered_fields.add("materials")
            self.answered_fields.add("preferred_materials")
        elif field_name in ("finish", "preferred_finish"):
            self.answered_fields.add("finish")
            self.answered_fields.add("preferred_finish")
        self.updated_at = time.time()

    def is_answered(self, field_name: str) -> bool:
        """Check whether a specific field has already been provided by customer."""
        if field_name in ("furniture_type", "project_type"):
            return "furniture_type" in self.answered_fields or "project_type" in self.answered_fields or bool(self.project_type)
        if field_name in ("materials", "preferred_materials"):
            return "materials" in self.answered_fields or "preferred_materials" in self.answered_fields or bool(self.preferred_materials)
        if field_name in ("finish", "preferred_finish"):
            return "finish" in self.answered_fields or "preferred_finish" in self.answered_fields or bool(self.preferred_finish)

        if field_name in self.answered_fields:
            return True
        val = getattr(self, field_name, None)
        if val is not None and val != "" and val != []:
            self.answered_fields.add(field_name)
            return True
        return False

    def update_field(self, field_name: str, value: Any) -> None:
        """Update a specific requirement field without resetting others."""
        if value is not None and value != "" and value != []:
            setattr(self, field_name, value)
            self.mark_answered(field_name)
            self.updated_at = time.time()

    def get_missing_field(self) -> Optional[str]:
        """Return the next unanswered discovery field in priority order."""
        for f in DISCOVERY_FIELDS_ORDER:
            # Map "materials" / "finish" to their respective attributes
            if f == "furniture_type" and not self.is_answered("project_type"):
                return "furniture_type"
            elif f == "dimensions" and not self.is_answered("dimensions"):
                return "dimensions"
            elif f == "materials" and not self.is_answered("preferred_materials"):
                return "materials"
            elif f == "finish" and not self.is_answered("preferred_finish"):
                return "finish"
        return None

    def transition_to(self, new_stage: ConversationStage | str, reason: str = "") -> None:
        """Safely transition to a new stage."""
        stage_val = new_stage.value if isinstance(new_stage, ConversationStage) else str(new_stage)
        if self.stage != stage_val:
            prev = self.stage
            self.stage = stage_val
            self.updated_at = time.time()
            if reason:
                self.notes.append(f"Stage transition {prev} -> {stage_val}: {reason}")
            logger.info(f"Customer {self.phone} transitioned: {prev} -> {stage_val} ({reason})")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        d = asdict(self)
        d["answered_fields"] = list(self.answered_fields)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CustomerEnquiryMemory:
        """Hydrate enquiry memory from dictionary."""
        ans = set(data.get("answered_fields") or [])
        mem = cls(
            phone=data.get("phone") or "",
            customer_name=data.get("customer_name"),
            stage=data.get("stage") or ConversationStage.NEW_ENQUIRY.value,
            project_type=data.get("project_type"),
            room_type=data.get("room_type"),
            dimensions=data.get("dimensions"),
            preferred_materials=data.get("preferred_materials") or [],
            preferred_finish=data.get("preferred_finish"),
            hardware_preference=data.get("hardware_preference"),
            customer_budget=data.get("customer_budget"),
            estimated_price=data.get("estimated_price"),
            timeline=data.get("timeline"),
            site_address=data.get("site_address"),
            locality=data.get("locality"),
            visit_slot=data.get("visit_slot"),
            consultation_mode=data.get("consultation_mode") or "in_person",
            human_handover=bool(data.get("human_handover", False)),
            answered_fields=ans,
            notes=data.get("notes") or [],
            last_intent=data.get("last_intent"),
            created_at=data.get("created_at") or time.time(),
            updated_at=data.get("updated_at") or time.time(),
        )
        # Populate answered fields if values are present
        if mem.project_type:
            mem.answered_fields.add("project_type")
            mem.answered_fields.add("furniture_type")
        if mem.dimensions:
            mem.answered_fields.add("dimensions")
        if mem.preferred_materials:
            mem.answered_fields.add("preferred_materials")
            mem.answered_fields.add("materials")
        if mem.preferred_finish:
            mem.answered_fields.add("preferred_finish")
            mem.answered_fields.add("finish")
        if mem.site_address:
            mem.answered_fields.add("site_address")
        if mem.visit_slot:
            mem.answered_fields.add("visit_slot")
        return mem


class StateMachine:
    """Manages stage transitions and conversation state for customer sessions."""

    def __init__(self) -> None:
        self._memories: Dict[str, CustomerEnquiryMemory] = {}

    def get_or_create(self, phone: str, customer_name: Optional[str] = None) -> CustomerEnquiryMemory:
        """Get or initialize customer memory."""
        clean_phone = re.sub(r"[^\d]", "", str(phone or ""))
        if clean_phone.startswith("00"):
            clean_phone = clean_phone[2:]
        if clean_phone not in self._memories:
            self._memories[clean_phone] = CustomerEnquiryMemory(
                phone=clean_phone,
                customer_name=customer_name,
            )
        mem = self._memories[clean_phone]
        if customer_name and not mem.customer_name:
            mem.customer_name = customer_name
        return mem

    def evaluate_transition(
        self,
        memory: CustomerEnquiryMemory,
        user_text: str,
        detected_intent: Optional[str] = None,
    ) -> str:
        """Determine next stage based on customer input, intent, and current memory state."""
        text_lower = user_text.lower()

        # 1. Human handover active?
        if memory.human_handover:
            memory.transition_to(ConversationStage.HUMAN_HANDOVER, "Human takeover active")
            return ConversationStage.HUMAN_HANDOVER.value

        # 2. Visit Confirmation: slot + address known
        if memory.visit_slot and memory.site_address:
            memory.transition_to(ConversationStage.VISIT_CONFIRMED, "Slot and address both recorded")
            return ConversationStage.VISIT_CONFIRMED.value

        # 3. Visit Requested: slot selected or address provided or scheduling intent
        if detected_intent == "visit_confirm" or memory.visit_slot or memory.site_address:
            memory.transition_to(ConversationStage.VISIT_REQUESTED, "Site visit requested or address given")
            return ConversationStage.VISIT_REQUESTED.value

        # 4. Negotiation / Bargaining
        if detected_intent == "bargaining" or any(
            k in text_lower for k in [
                "discount", "kam karo", "budget kam", "thoda kam", "sasta", "cheaper",
                "too high", "expensive", "mahanga", "mehanga", "ochu karo", "thodu kam"
            ]
        ):
            memory.transition_to(ConversationStage.NEGOTIATION, "Customer requested discount or lower price")
            return ConversationStage.NEGOTIATION.value

        # 5. Estimation / Price Discussion
        if detected_intent in ("final_price", "price_quote") or any(
            k in text_lower for k in [
                "final price", "final cost", "what price", "kya price", "kitna kharcha",
                "how much", "rate kya hai", "estimate", "quotation", "quote"
            ]
        ):
            memory.transition_to(ConversationStage.ESTIMATION, "Price estimate requested")
            return ConversationStage.ESTIMATION.value

        # 6. Budget Discussion: customer shares budget figure
        if memory.customer_budget:
            memory.transition_to(ConversationStage.BUDGET_DISCUSSION, "Customer shared budget figure")
            return ConversationStage.BUDGET_DISCUSSION.value

        # 7. Project Discovery: furniture type known, exploring dimensions/details
        if memory.project_type and memory.dimensions:
            memory.transition_to(ConversationStage.PROJECT_DISCOVERY, "Item and dimensions identified")
            return ConversationStage.PROJECT_DISCOVERY.value

        # 8. Requirement Collection: furniture type known, awaiting dimensions
        if memory.project_type:
            memory.transition_to(ConversationStage.REQUIREMENT_COLLECTION, "Furniture type identified")
            return ConversationStage.REQUIREMENT_COLLECTION.value

        # 9. Greeting / New Enquiry
        if memory.stage == ConversationStage.NEW_ENQUIRY.value:
            memory.transition_to(ConversationStage.GREETING, "Initial greeting")
            return ConversationStage.GREETING.value

        return memory.stage


# Global singleton
state_machine = StateMachine()
