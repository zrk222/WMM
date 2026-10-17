"""Observed transaction lifecycle only: configured prices never become inferred proceeds."""
from .common import digest

PURCHASES={"SUBSCRIBED","DID_RENEW","ONE_TIME_CHARGE"}
KNOWN=PURCHASES|{"REFUND","REFUND_REVERSED","REVOKE"}
IDENTITY=("original_transaction_id","product_id","purchase_date","currency","price_milliunits")


def conflict(items):
    """Require consistent known immutable fields and a unique state at each signed timestamp."""
    items=[item for item in items if item["notification_type"] in KNOWN]
    for field in IDENTITY:
        values={item["transaction"][field] for item in items if item["transaction"][field] is not None}
        if len(values)>1:return "Immutable transaction field differs: "+field
    stamps={}
    for item in items:
        if item["notification_type"] not in KNOWN:continue
        state=semantic_state(item)
        previous=stamps.setdefault(item["signed_date"],state)
        if previous!=state:return "Equal signing date has conflicting observed states"
    return None


def semantic_state(item):
    """Treat equivalent purchase kinds equally, but keep refund type/percentage distinct."""
    kind=item["notification_type"]
    tx=item["transaction"]
    if kind in PURCHASES:return ("PURCHASE_OBSERVED",)
    return (kind,tx["revocation_type"],tx["revocation_percentage_milliunits"])


def lifecycle(items):
    """Replay ordered observations; reversals cannot invent an antecedent refund."""
    state="UNSUPPORTED";refund_seen=False
    for item in sorted(items,key=lambda row:(row["signed_date"],row["notification_id"])):
        kind=item["notification_type"];tx=item["transaction"]
        if kind in PURCHASES and state=="UNSUPPORTED":state="PURCHASE_OBSERVED"
        elif kind=="REFUND":
            refund_seen=True
            state={"REFUND_FULL":"REFUND_FULL_OBSERVED","REFUND_PRORATED":"REFUND_PARTIAL_AMOUNT_UNKNOWN",
                   "FAMILY_REVOKE":"FAMILY_REVOKED"}.get(tx["revocation_type"],"REFUND_AMOUNT_UNKNOWN")
        elif kind=="REFUND_REVERSED":
            state="REFUND_REVERSED_OBSERVED" if refund_seen else "PENDING_REVERSAL"
        elif kind=="REVOKE":state="FAMILY_REVOKED" if tx["ownership"]=="FAMILY_SHARED" else "REVOKED_OBSERVED"
    return state


def transaction_report(key,items):
    """Count known configured price once only when a purchased ownership was observed."""
    problem=conflict(items)
    purchases=[i["transaction"] for i in items if i["notification_type"] in PURCHASES]
    paid=[tx for tx in purchases if tx["ownership"]=="PURCHASED" and not tx["advanced_commerce"]]
    priced=[tx for tx in paid if tx["price_milliunits"] is not None]
    chosen=priced[0] if priced and not problem else None
    return {"bundle_id":key[0],"environment":key[1],"transaction_id":key[2],
            "status":"CONFLICT" if problem else lifecycle(items),"conflict":problem,
            "notification_count":len(items),"purchase_observed":bool(purchases),"purchased_ownership_observed":bool(paid),
            "configured_price_milliunits":chosen["price_milliunits"] if chosen else None,
            "currency":chosen["currency"] if chosen else None,"fees":None,"net_proceeds":None,"attribution":"UNKNOWN",
            "verification_scope":"HISTORICAL_ASSERTION_ONLY" if any(i.get("_imported") for i in items) else "CURRENT_NATIVE_SIGNATURE_CHECKS"}


def report(receipts):
    """Group exact app/bundle/environment transaction identities without joining payment totals."""
    groups={};unsupported=0
    for row in receipts:
        item=dict(row["data"]["notification"]);item["_imported"]=bool(row["imported"])
        if item["transaction"] is None:
            unsupported+=1;continue
        key=(item["bundle_id"],item["environment"],item["transaction"]["transaction_id"])
        groups.setdefault(key,[]).append(item)
    transactions=[transaction_report(key,items) for key,items in sorted(groups.items())]
    sums={}
    for row in transactions:
        if row["configured_price_milliunits"] is None:continue
        key=(row["environment"],row["currency"])
        total=sums.setdefault(key,{"environment":key[0],"currency":key[1],"observed_configured_price_milliunits":0,"unique_priced_transactions":0})
        total["observed_configured_price_milliunits"]+=row["configured_price_milliunits"];total["unique_priced_transactions"]+=1
    return {"status":"NO_DATA" if not receipts else "OBSERVED_CONFIGURED_PRICES_ONLY","transactions":transactions,
            "configured_price_observations":list(sums.values()),"nontransaction_notifications":unsupported,
            "verification_scope":"HISTORICAL_ASSERTION_ONLY" if any(row["imported"] for row in receipts) else "CURRENT_NATIVE_SIGNATURE_CHECKS",
            "net_proceeds":None,"refund_amounts":None,"attribution":"UNKNOWN",
            "interpretation":"Configured transaction prices and observed lifecycle only. Not account revenue, cash, fees, entitlement state or causal growth. Sandbox and Production remain separate."}
