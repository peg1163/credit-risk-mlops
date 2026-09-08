import json
from credit_risk.evaluation import evaluate
print(json.dumps(evaluate(),indent=2,default=str))
