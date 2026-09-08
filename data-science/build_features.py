import argparse
from credit_risk.dataset import build_and_save, build_incoming_features
if __name__=="__main__":
 p=argparse.ArgumentParser(); p.add_argument("--source",choices=["archive","incoming"],default="archive"); a=p.parse_args()
 print(build_and_save() if a.source=="archive" else build_incoming_features())
