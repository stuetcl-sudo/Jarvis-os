def explain_match(policy, event, asset, matched: bool, allowed: bool, action: str, reason: str) -> str:
    asset_id = (asset or {}).get("asset_id") or getattr(event, "asset_id", None) or getattr(event, "service", None)
    classification = (asset or {}).get("classification", "unknown")
    state = (asset or {}).get("state", "unknown")
    return (
        f"Policy '{policy['name']}' evaluated event '{event.type}' for asset '{asset_id}'. "
        f"Asset classification='{classification}', state='{state}'. "
        f"Matched={matched}. Allowed={allowed}. Action='{action}'. Reason: {reason}"
    )
