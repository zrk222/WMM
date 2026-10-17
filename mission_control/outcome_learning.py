"""Authenticated, versioned local guidance with explicit adoption, use and rollback."""
import copy
import json
from .common import Invalid,canonical,digest,now,required,uid
from .db import connection
from .learning_contract import declare,training,app_hash,active_id,reserve_role,source_current,holdout,evaluation,eligible
from .outcome_links import Links,decoded
from .review_access import member,exact_role
from .creative_briefs import bind as bind_brief
from .creative_analysis import append as append_brief

STATES={"PROPOSED","RESERVED","READY","REJECTED","APPROVED","ACTIVE","SUPERSEDED","ROLLED_BACK"}


def find(db,app_id,identity):
    """Read the exact scoped immutable program snapshot and integrity hash."""
    row=db.execute("SELECT * FROM learning_programs WHERE app_id=? AND id=?",(app_id,identity)).fetchone()
    if not row:raise Invalid("Learning program does not belong to this workspace")
    result=dict(row);result["data"]=json.loads(result["data"])
    if digest(result["data"])!=result["hash"]:raise Invalid("Learning program integrity failed")
    return result


def expected(row,body,fields):
    """Bind each action to the exact inspected optimistic version and hash."""
    if set(body)!=set(fields)|{"version","hash"}:raise Invalid("Complete the exact learning action fields")
    if type(body["version"]) is not int or body["version"]!=row["version"] or body["hash"]!=row["hash"]:raise Invalid("Learning version changed; reload before continuing")


def maker(db,row,user):
    """Only the original current maker may advance this proposal."""
    role=exact_role(db,row["app_id"],row["preparer"],row["data"]["maker_role_version"],"MAKER")
    if user["principal"]!=role["principal"]:raise PermissionError("Continue this proposal as its original maker")
    return role


def transition(db,row,status,data,operation,actor):
    """Append exact receipts before changing the materialized current state."""
    if status not in STATES:raise Invalid("Unknown local guidance state")
    history_capacity(db,row["app_id"])
    version=row["version"]+1;stamp=now()
    event={"operation":operation,"actor":actor,"previous_hash":row["hash"],"state":status,"data":data,"created":stamp}
    db.execute("INSERT INTO learning_events VALUES(?,?,?,?,?,?)",(row["app_id"],row["id"],version,canonical(event),digest(event),stamp))
    db.execute("UPDATE learning_programs SET data=?,hash=?,state=?,version=?,updated=? WHERE app_id=? AND id=?",
               (canonical(data),digest(data),status,version,stamp,row["app_id"],row["id"]))
    return find(db,row["app_id"],row["id"])


def history_capacity(db,app_id):
    """Apply the same bounded receipt capacity to proposals and later transitions."""
    count=db.execute("SELECT count(*) FROM learning_events WHERE app_id=?",(app_id,)).fetchone()[0]
    if count>=5000:raise Invalid("Archive learning history before 5000 transitions")


def history(db,row):
    """Show exact immutable transitions, rejecting hash corruption."""
    result=[]
    for record in db.execute("SELECT * FROM learning_events WHERE app_id=? AND learning_id=? ORDER BY version",(row["app_id"],row["id"])):
        item=dict(record);item["data"]=json.loads(item["data"])
        if digest(item["data"])!=item["hash"]:raise Invalid("Learning receipt integrity failed")
        check_receipt(item,result,row)
        result.append(item)
    if not result or result[-1]["version"]!=row["version"] or result[-1]["data"]["data"]!=row["data"] or result[-1]["data"]["state"]!=row["state"]:raise Invalid("Learning history does not match its current version")
    return result


def check_receipt(item,previous,row):
    """Reject missing/reordered transitions and broken hash linkage on normal reads."""
    value=item["data"];version=len(previous)+1
    if item["version"]!=version or value["created"]!=item["created"]:raise Invalid("Learning receipt sequence changed")
    if not previous:
        if value["operation"]!="propose" or value["state"]!="PROPOSED" or value["previous_hash"] is not None:raise Invalid("Learning history has no original proposal")
    elif value["previous_hash"]!=digest(previous[-1]["data"]["data"]):raise Invalid("Learning prior receipt hash changed")


def available(db,store,row,context=None):
    """Preserve saved state while deriving current usable authority."""
    issues=[]
    try:
        if row["state"] in ("READY","APPROVED","ACTIVE","SUPERSEDED"):eligible(db,store,row,row["state"] in ("APPROVED","ACTIVE","SUPERSEDED"),context)
        else:source_current(db,store,row,context)
    except (Invalid,PermissionError,OSError,KeyError) as exc:issues.append(str(exc) if isinstance(exc,(Invalid,PermissionError)) else "A required learning source is unavailable")
    return issues


class Learning:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Expose actual states, current source truth and protected active guidance."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN"); pointer=active_id(db,app_id);items=[];context={}
            for identity in db.execute("SELECT id FROM learning_programs WHERE app_id=? ORDER BY created DESC,id LIMIT 1000",(app_id,)).fetchall():
                row=find(db,app_id,identity[0]);row["events"]=history(db,row);row["findings"]=available(db,self.store,row,context)
                row["availability"]="UNAVAILABLE" if row["findings"] else "CURRENT"
                row["active"]=row["id"]==pointer and row["state"]=="ACTIVE" and not row["findings"];items.append(row)
            uses=[decoded(r) for r in db.execute("SELECT * FROM learning_brief_uses WHERE app_id=? ORDER BY created DESC LIMIT 1000",(app_id,))]
        return {"programs":items,"links":Links(self.store).list(app_id),"cost_options":Links(self.store).options(app_id),
                "active_id":pointer,"uses":uses,"scope":"Supplied descriptive outcomes and explicit local creative guidance; external execution not authorized"}

    def propose(self,app_id,user,body):
        """Freeze current mature training and an original declared creative method."""
        self.store.app(app_id);definition=declare(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");role=member(db,app_id,user["principal"],"MAKER")
            if db.execute("SELECT count(*) FROM learning_programs WHERE app_id=?",(app_id,)).fetchone()[0]>=1000:raise Invalid("Archive learning programs before 1000 proposals")
            source=training(db,self.store,app_id,definition["training_experiment_id"])
            history_capacity(db,app_id)
            identity=uid();stamp=now();reserve_role(db,app_id,source["experiment"]["id"],"TRAIN",identity)
            data={"definition":definition,"app_hash":app_hash(db,app_id),"training":source,"training_hash":digest(source),
                  "maker_role_version":role["version"],"previous_id":active_id(db,app_id)}
            db.execute("INSERT INTO learning_programs VALUES(?,?,?,?,?,?,?,?,?,?)",(app_id,identity,canonical(data),digest(data),"PROPOSED",1,user["principal"],0,stamp,stamp))
            event={"operation":"propose","actor":user["principal"],"previous_hash":None,"state":"PROPOSED","data":data,"created":stamp}
            db.execute("INSERT INTO learning_events VALUES(?,?,?,?,?,?)",(app_id,identity,1,canonical(event),digest(event),stamp))
            return find(db,app_id,identity)

    def act(self,app_id,identity,user,operation,body):
        """Dispatch only named local actions with fresh app-scoped role authority."""
        self.store.app(app_id)
        actions={"reserve":self.reserve,"evaluate":self.evaluate,"approve":self.approve,"activate":self.activate,"rollback":self.rollback}
        if operation not in actions:raise Invalid("Unknown local learning action")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");row=find(db,app_id,identity)
            history(db,row);member(db,app_id,user["principal"])
            return actions[operation](db,row,user,body)

    def reserve(self,db,row,user,body):
        """Freeze the untouched future design before its first observed event."""
        expected(row,body,{"experiment_id","control_brief_id","treatment_brief_id","confirm_pattern_test"});maker(db,row,user)
        if row["state"]!="PROPOSED" or body["confirm_pattern_test"] is not True:raise Invalid("Confirm one new holdout for this proposed creative method")
        source_current(db,self.store,row);reserved=holdout(db,self.store,row,body)
        reserve_role(db,row["app_id"],reserved["experiment"]["id"],"HOLDOUT",row["id"])
        return transition(db,row,"RESERVED",dict(row["data"],holdout=reserved),"reserve",user["principal"])

    def evaluate(self,db,row,user,body):
        """Persist actual eligible or rejected descriptive holdout evidence."""
        expected(row,body,set());maker(db,row,user)
        if row["state"] not in ("RESERVED","READY","REJECTED"):raise Invalid("Evaluate a reserved holdout before approval or activation")
        try:result=evaluation(db,self.store,row)
        except Invalid as exc:result={"outcome":"REJECTED","issues":[str(exc)],"scope":"Required supplied evidence unavailable; no learning adoption"}
        return transition(db,row,result["outcome"],dict(row["data"],evaluation=result,evaluation_hash=digest(result)),"evaluate",user["principal"])

    def approve(self,db,row,user,body):
        """A distinct current checker authorizes only the exact local guidance."""
        expected(row,body,{"confirm_local_guidance"})
        role=member(db,row["app_id"],user["principal"],"CHECKER")
        if row["state"]!="READY" or body["confirm_local_guidance"] is not True or user["principal"]==row["preparer"]:raise Invalid("A different checker must explicitly approve this READY local guidance")
        eligible(db,self.store,row)
        approval={"principal":user["principal"],"role_version":role["version"],"reviewed_hash":row["hash"],"reviewed_version":row["version"]}
        return transition(db,row,"APPROVED",dict(row["data"],approval=approval),"approve",user["principal"])

    def activate(self,db,row,user,body):
        """Move the actual local guidance pointer after separate final confirmation."""
        expected(row,body,{"confirm_activate"});maker(db,row,user)
        if row["state"]!="APPROVED" or body["confirm_activate"] is not True:raise Invalid("Explicitly activate independently approved guidance")
        eligible(db,self.store,row,True);app_id=row["app_id"];previous=active_id(db,app_id)
        if previous!=row["data"]["previous_id"]:raise Invalid("Active guidance baseline changed; prepare a new proposal")
        if previous:
            prior=find(db,app_id,previous)
            transition(db,prior,"SUPERSEDED",prior["data"],"supersede",user["principal"])
        result=transition(db,row,"ACTIVE",row["data"],"activate",user["principal"])
        db.execute("INSERT INTO learning_active VALUES(?,?) ON CONFLICT(app_id) DO UPDATE SET learning_id=excluded.learning_id",(app_id,row["id"]))
        return result

    def rollback(self,db,row,user,body):
        """Execute local influence rollback, never claim a provider rollback."""
        expected(row,body,{"confirm_rollback","reason"});role=member(db,row["app_id"],user["principal"],"MAKER")
        if user["principal"]!=row["preparer"] and role["role"]!="OWNER":raise PermissionError("Only the original maker or app owner can roll back this guidance")
        if row["state"]!="ACTIVE" or active_id(db,row["app_id"])!=row["id"] or body["confirm_rollback"] is not True:raise Invalid("Confirm rollback of the actual active guidance")
        reason=required(body["reason"],"Rollback reason",2000);restored=None;previous=row["data"]["previous_id"]
        if previous:
            prior=find(db,row["app_id"],previous)
            if prior["state"]=="SUPERSEDED" and not available(db,self.store,prior):
                transition(db,prior,"ACTIVE",prior["data"],"restore",user["principal"]);restored=previous
        data=dict(row["data"],rollback={"reason":reason,"restored_id":restored,"external_execution":"NOT_RUN"})
        result=transition(db,row,"ROLLED_BACK",data,"rollback",user["principal"])
        db.execute("UPDATE learning_active SET learning_id=? WHERE app_id=?",(restored,row["app_id"]))
        return result

    def use(self,app_id,identity,user,body):
        """Apply disclosed guidance only to a new proof-bound original brief."""
        if set(body)!={"data","version","hash"}:raise Invalid("Use the exact active guidance with a new brief")
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");row=find(db,app_id,identity);expected(row,body,{"data"});history(db,row);member(db,app_id,user["principal"],"MAKER")
            if row["state"]!="ACTIVE" or active_id(db,app_id)!=identity:raise Invalid("This guidance is no longer active")
            eligible(db,self.store,row,True)
            if db.execute("SELECT count(*) FROM learning_brief_uses WHERE app_id=?",(app_id,)).fetchone()[0]>=1000:raise Invalid("Archive learning use receipts before 1000 briefs")
            requested=copy.deepcopy(body["data"]);objective=required(requested.get("objective"),"Original objective",2000)
            requested["objective"]=required(objective+"\n\nCreative method to test: "+row["data"]["definition"]["pattern"],"Combined objective",2000)
            brief=append_brief(db,"creative_briefs",app_id,bind_brief(db,self.store,app_id,requested),{"data":requested})
            receipt={"brief_id":brief["id"],"brief_hash":brief["hash"],"learning_id":identity,"learning_hash":row["hash"],"evaluation_hash":row["data"]["evaluation_hash"],
                     "operator":user["principal"],"mode":"EXPLICIT_NEW_BRIEF_ONLY","external_execution":"NOT_RUN"}
            db.execute("INSERT INTO learning_brief_uses VALUES(?,?,?,?,?,?)",(app_id,brief["id"],identity,canonical(receipt),digest(receipt),now()))
            return {"brief":brief,"receipt":receipt}
