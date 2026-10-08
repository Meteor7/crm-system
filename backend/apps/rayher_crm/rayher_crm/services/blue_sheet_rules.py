"""Lossless red-flag compatibility and explicitly configured probability rules.

There is deliberately no default mapping from stakeholder/risk facts to a level.
Business-approved site configuration supplies an ordered, versioned rule set.
"""
from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
import json

from rayher_crm.services.opportunity_stages import PROBABILITY_LEVELS

SEVERITIES = ("", "Low", "Medium", "High")
STATUSES = ("Open", "Resolved")
ROLES = ("Decision Maker", "Economic Buyer", "Technical Buyer", "User Buyer", "Coach", "Procurement", "Influencer", "Champion", "Technical Champion", "Primary Contact")


def decode(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    return value if isinstance(value, list) else []


def red_flags(opportunity_id, stored, legacy):
    if stored not in (None, ""):
        return [dict(row) for row in decode(stored)]
    return [{"id": "legacy-" + sha256(f"{opportunity_id}\0{index}\0{text}".encode()).hexdigest()[:24],
             "text": text, "severity": "", "status": "Open", "updatedAt": None, "updatedBy": None}
            for index, text in enumerate(decode(legacy))]


def reconcile_legacy(records, texts, new_id, at, actor):
    """Old text editors preserve metadata for each unchanged text occurrence."""
    by_text = defaultdict(deque)
    for row in records:
        by_text[row["text"]].append(row)
    items = []
    for text in texts:
        previous = by_text[text].popleft() if by_text[text] else None
        items.append({key: previous[key] for key in ("id", "text", "severity", "status")} if previous else
                     {"text": text, "severity": "", "status": "Open"})
    # Both the old API and the structured editor share the same legacy exceptions.
    return update_flags(records, items, new_id, at, actor)


def update_flags(records, raw, new_id, at, actor):
    if not isinstance(raw, list) or len(raw) > max(200, len(records)):
        raise ValueError("Choose a list of at most 200 red flags; larger legacy lists may be retained.")
    old = {row["id"]: row for row in records}
    seen, result = set(), []
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"id", "text", "severity", "status"}:
            raise ValueError("Each red flag needs text, severity and status, with an optional existing id.")
        identity = item.get("id")
        if identity is not None and (not isinstance(identity, str) or identity not in old or identity in seen):
            raise ValueError("Red flag ids must be distinct existing ids.")
        previous = old.get(identity)
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() or (len(text) > 4000 and (not previous or text != previous["text"])):
            raise ValueError("Red flag text needs 1–4000 characters; unchanged legacy text is retained.")
        severity, status = item.get("severity"), item.get("status")
        if severity not in SEVERITIES or status not in STATUSES:
            raise ValueError("Choose a supported severity and handling status.")
        identity = identity or new_id()
        seen.add(identity)
        unchanged = previous and (text, severity, status) == (previous["text"], previous["severity"], previous["status"])
        result.append(dict(previous) if unchanged else {"id": identity, "text": text, "severity": severity,
                      "status": status, "updatedAt": at, "updatedBy": actor})
    return result


def configured_rules(raw):
    """Validate the entire rule set before any rule can produce a suggestion."""
    if not isinstance(raw, dict) or set(raw) != {"version", "rules"}:
        return None
    if not isinstance(raw["version"], str) or not 1 <= len(raw["version"].strip()) <= 100:
        return None
    if not isinstance(raw["rules"], list) or not 1 <= len(raw["rules"]) <= 40:
        return None
    seen = set()
    keys = {"id", "level", "requiredRoles", "supportingRoles", "maxOpenRedFlags", "maxHighRedFlags", "maxOpposedStakeholders", "requireClassifiedRedFlags", "reason"}
    for rule in raw["rules"]:
        if not isinstance(rule, dict) or set(rule) != keys:
            return None
        if not isinstance(rule["id"], str) or not 1 <= len(rule["id"]) <= 100 or rule["id"] in seen:
            return None
        seen.add(rule["id"])
        if rule["level"] not in PROBABILITY_LEVELS or not isinstance(rule["reason"], str) or not 1 <= len(rule["reason"].strip()) <= 1000:
            return None
        if any(not isinstance(rule[key], list) or any(role not in ROLES for role in rule[key]) or len(set(rule[key])) != len(rule[key]) for key in ("requiredRoles", "supportingRoles")):
            return None
        if any(type(rule[key]) is not int or not 0 <= rule[key] <= 10000 for key in ("maxOpenRedFlags", "maxHighRedFlags", "maxOpposedStakeholders")):
            return None
        if type(rule["requireClassifiedRedFlags"]) is not bool:
            return None
    return raw


def assess(records, stakeholders, config):
    active = [row for row in records if row["status"] == "Open"]
    roles = sorted({row["role"] for row in stakeholders if row.get("role") in ROLES})
    supporters = sorted({row["role"] for row in stakeholders if row.get("stance") == "Support" and row.get("role") in ROLES})
    facts = {"openRedFlags": len(active), "highRedFlags": sum(row["severity"] == "High" for row in active),
             "unclassifiedRedFlags": sum(not row["severity"] for row in active),
             "opposedStakeholders": sum(row.get("stance") == "Against" for row in stakeholders),
             "coveredRoles": roles, "supportingRoles": supporters}
    rules = configured_rules(config)
    result = {"state": "unconfigured" if rules is None else "no_match", "ruleVersion": rules["version"] if rules else None,
              "ruleId": None, "suggestedLevel": None, "reason": None, "facts": facts}
    if rules:
        for rule in rules["rules"]:
            if (set(rule["requiredRoles"]) <= set(roles) and set(rule["supportingRoles"]) <= set(supporters)
                and facts["openRedFlags"] <= rule["maxOpenRedFlags"] and facts["highRedFlags"] <= rule["maxHighRedFlags"]
                and facts["opposedStakeholders"] <= rule["maxOpposedStakeholders"]
                and (not rule["requireClassifiedRedFlags"] or facts["unclassifiedRedFlags"] == 0)):
                result.update(state="suggested", ruleId=rule["id"], suggestedLevel=rule["level"], reason=rule["reason"])
                break
    return result


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
