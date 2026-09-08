from __future__ import annotations
import argparse, json, shutil
from datetime import datetime, timezone
from pathlib import Path
from .common import DATA, config, sha256, write_json

STATE=DATA/"replay_state.json"; ARCHIVE=DATA/"raw_archive"/"transactions"; INCOMING=DATA/"incoming"/"transactions"; MANIFESTS=DATA/"manifests"
def periods(): return [p.name.split("=",1)[1] for p in sorted(ARCHIVE.glob("period=*")) if p.name.split("=",1)[1] >= config()["splits"]["replay_start"][:7]]
def state(): return json.loads(STATE.read_text()) if STATE.exists() else {"dataset_id":config()["dataset_id"],"released":[],"simulated_date":None}
def release(period: str) -> dict:
    s=state()
    if period in s["released"]: raise ValueError(f"Period already released: {period}")
    if period not in periods(): raise ValueError(f"Unavailable replay period: {period}")
    if s["released"] and period <= max(s["released"]): raise ValueError("Replay must advance monotonically")
    src=ARCHIVE/f"period={period}"/"data.parquet"; dst=INCOMING/f"period={period}"/"data.parquet"
    reference=DATA/"incoming"/"reference"
    if not reference.exists():
      reference.mkdir(parents=True)
      for name in ["loan.parquet","account.parquet"]: shutil.copy2(DATA/"raw_archive"/name,reference/name)
    dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    if sha256(src)!=sha256(dst): raise IOError("Integrity check failed after release")
    import pandas as pd
    frame=pd.read_parquet(dst)
    manifest={"dataset_id":config()["dataset_id"],"period":period,"rows":len(frame),"accounts":frame.account_id.nunique(),"sha256":sha256(dst),"released_at_utc":datetime.now(timezone.utc).isoformat(),"source_partition":str(src.relative_to(DATA)),"destination_partition":str(dst.relative_to(DATA))}
    write_json(MANIFESTS/f"batch-{period}.json",manifest)
    s["released"].append(period); s["simulated_date"]=f"{period}-01"; write_json(STATE,s)
    return manifest
def reset():
    if INCOMING.exists(): shutil.rmtree(INCOMING)
    if MANIFESTS.exists(): shutil.rmtree(MANIFESTS)
    if STATE.exists(): STATE.unlink()
def main():
    p=argparse.ArgumentParser(); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--release-month"); g.add_argument("--next",action="store_true"); g.add_argument("--reset",action="store_true"); g.add_argument("--status",action="store_true")
    a=p.parse_args()
    if a.reset: reset(); print("reset")
    elif a.status: print(json.dumps(state(),indent=2))
    else:
      per=a.release_month
      if a.next:
        remaining=[x for x in periods() if x not in state()["released"]]
        if not remaining: raise SystemExit("No periods remaining")
        per=remaining[0]
      print(json.dumps(release(per),indent=2))
if __name__=="__main__": main()
