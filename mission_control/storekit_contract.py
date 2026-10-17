"""Bound verified StoreKit claims to app identity and retain only permitted transaction facts."""
import re
import time
import uuid
from .common import Invalid
from .storekit_jws import verified_object

TRANSACTION_TYPES={"SUBSCRIBED","DID_RENEW","ONE_TIME_CHARGE","REFUND","REFUND_REVERSED","REVOKE"}
OWNERSHIP={"PURCHASED","FAMILY_SHARED"}
REVOCATIONS={"REFUND_FULL","REFUND_PRORATED","FAMILY_REVOKE"}
TRANSACTION_FIELDS={"transaction_id","original_transaction_id","product_id","purchase_date","signed_date",
                    "expires_date","ownership","price_milliunits","currency","quantity","transaction_type",
                    "revocation_type","revocation_percentage_milliunits","revocation_date","advanced_commerce"}
NOTIFICATION_FIELDS={"notification_id","notification_type","subtype","signed_date","bundle_id",
                     "app_apple_id","environment","transaction"}


def integer(value, name, low=1, high=1000000000000):
    """Reject boolean/coerced numbers and preserve bounded exact integer units."""
    if type(value) is not int or not low<=value<=high:
        raise Invalid("StoreKit "+name+" is invalid")
    return value


def text(value,name,limit,pattern=None):
    """Reject controls, oversized labels and path-like identities without reflecting data."""
    if not isinstance(value,str) or not 1<=len(value)<=limit or not value.isprintable():
        raise Invalid("StoreKit "+name+" is invalid")
    if pattern and not re.fullmatch(pattern,value):
        raise Invalid("StoreKit "+name+" format is invalid")
    return value


def canonical_uuid(value):
    """Normalize UUID case only; reject noncanonical separators and other representations."""
    text(value,"notification UUID",36)
    try:result=str(uuid.UUID(value))
    except (ValueError,AttributeError) as exc:raise Invalid("StoreKit notification UUID is invalid") from exc
    if result!=value.lower():
        raise Invalid("StoreKit notification UUID must use canonical separators")
    return result


def declaration(body):
    """Persist only explicit source identity and certificate-network consent."""
    fields={"bundle_id","app_apple_id","environment","confirm_read"}
    if not isinstance(body,dict) or set(body)!=fields or body["confirm_read"] is not True:
        raise Invalid("Confirm online certificate checks and provide the declared app identity")
    bundle=text(body["bundle_id"],"bundle ID",255,r"[A-Za-z0-9.-]+")
    value=body["app_apple_id"]
    if isinstance(value,str):
        if not re.fullmatch(r"[0-9]{1,30}",value):raise Invalid("Enter a numeric Apple app ID")
        value=int(value)
    value=integer(value,"Apple app ID",high=10**30-1)
    environment=body["environment"]
    if environment not in ("Sandbox","Production"):raise Invalid("Choose Sandbox or Production")
    return {"bundle_id":bundle,"app_apple_id":value,"environment":environment}


def date(value,name,clock,future=300000):
    """Use provider milliseconds without accepting future-dated or coerced observations."""
    return integer(value,name,high=int(clock*1000)+future)


def scope(data,config,notification=True):
    """Require both verified carriers to identify this exact bundle/environment."""
    if data.get("bundleId")!=config["bundle_id"] or data.get("environment")!=config["environment"]:
        raise Invalid("StoreKit app bundle or environment does not match this source")
    apple=data.get("appAppleId")
    if (notification and config["environment"]=="Production") or apple is not None:
        if type(apple) is not int or apple!=config["app_apple_id"]:
            raise Invalid("StoreKit Apple app ID does not match this source")


def carrier(outer):
    """Use exactly one metadata carrier; unsupported carriers cannot bypass source scope."""
    names=("data","summary","externalPurchaseToken","appData")
    present=[name for name in names if outer.get(name) is not None]
    if len(present)!=1 or not isinstance(outer[present[0]],dict):
        raise Invalid("StoreKit notification must have one app metadata carrier")
    data=dict(outer[present[0]])
    if present[0]=="externalPurchaseToken" and "environment" not in data:
        purchase=text(data.get("externalPurchaseId"),"external purchase ID",255)
        data["environment"]="Sandbox" if purchase.startswith("SANDBOX") else "Production"
    return data


def optional_enum(data,key,allowed):
    """Unknown enum is an unsupported contract, never a silently inferred paid state."""
    value=data.get(key)
    if value is not None and value not in allowed:
        raise Invalid("StoreKit "+key+" is unsupported")
    return value


def price(data):
    """Configured price is milliunits, not cash or proceeds; absence stays unknown."""
    amount,currency=data.get("price"),data.get("currency")
    if amount is None and currency is None:return None,None
    integer(amount,"price",0)
    text(currency,"currency",3,r"[A-Z]{3}")
    return amount,currency


def optional_date(data,key,clock,future=300000):
    """Retain unknown times as null rather than synthesizing lifecycle dates."""
    return date(data[key],key,clock,future) if data.get(key) is not None else None


def transaction(data,config,clock):
    """Sanitize an independently verified transaction without identity/contact metadata."""
    scope(data,config,notification=False)
    amount,currency=price(data)
    purchased=date(data.get("purchaseDate"),"purchaseDate",clock)
    signed=date(data.get("signedDate"),"transaction signedDate",clock)
    if purchased>signed:raise Invalid("StoreKit purchase date follows its signing date")
    result={"transaction_id":text(data.get("transactionId"),"transaction ID",40,r"[0-9]+"),
            "original_transaction_id":text(data.get("originalTransactionId"),"original transaction ID",40,r"[0-9]+"),
            "product_id":text(data.get("productId"),"product ID",255),"purchase_date":purchased,"signed_date":signed,
            "expires_date":optional_date(data,"expiresDate",clock,3155760000000),
            "ownership":optional_enum(data,"inAppOwnershipType",OWNERSHIP),"price_milliunits":amount,"currency":currency,
            "quantity":integer(data["quantity"],"quantity",high=1000000) if data.get("quantity") is not None else None,
            "transaction_type":text(data["type"],"transaction type",80) if data.get("type") is not None else None,
            "revocation_type":optional_enum(data,"revocationType",REVOCATIONS),
            "revocation_percentage_milliunits":integer(data["revocationPercentage"],"revocation percentage",0,100000) if data.get("revocationPercentage") is not None else None,
            "revocation_date":optional_date(data,"revocationDate",clock),"advanced_commerce":data.get("advancedCommerceInfo") is not None}
    return result


def normalize(compact,config,verifier=verified_object,clock=None):
    """Verify outer and every supplied nested transaction separately before retaining claims."""
    clock=time.time() if clock is None else clock
    outer=verifier(compact)
    if outer.get("version")!="2.0":raise Invalid("Use StoreKit notification version 2.0")
    kind=text(outer.get("notificationType"),"notification type",80,r"[A-Z0-9_]+")
    data=carrier(outer);scope(data,config)
    nested=data.get("signedTransactionInfo")
    if kind in TRANSACTION_TYPES and nested is None:
        raise Invalid("StoreKit transaction notification lacks its signed transaction")
    tx=transaction(verifier(nested),config,clock) if nested is not None else None
    subtype=text(outer["subtype"],"notification subtype",80,r"[A-Z0-9_]+") if outer.get("subtype") is not None else None
    return {"notification_id":canonical_uuid(outer.get("notificationUUID")),"notification_type":kind,"subtype":subtype,
            "signed_date":date(outer.get("signedDate"),"notification signedDate",clock),
            "bundle_id":config["bundle_id"],"app_apple_id":data.get("appAppleId"),"environment":config["environment"],
            "transaction":tx}
