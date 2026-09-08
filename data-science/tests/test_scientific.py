import pandas as pd
from credit_risk.common import DATA, config
from credit_risk.dataset import FEATURES
from credit_risk.modeling import split

def data(): return pd.read_parquet(DATA/"modeling_dataset.parquet")
def test_no_direct_outcome_or_future_features():
    forbidden={"status","event_date","target","label_maturity_date"}
    assert forbidden.isdisjoint(FEATURES)
def test_labels_only_use_strict_future_horizon():
    d=data(); positive=d[d.target.eq(1)]
    assert (positive.event_date>positive.observation_date).all()
    assert (positive.event_date<=positive.label_maturity_date).all()
def test_maturity_and_availability():
    d=data(); assert (d.data_available_date<=d.observation_date).all()
    assert (d.loc[d.is_mature,"label_maturity_date"]<=pd.Timestamp("1998-12-31")).all()
def test_chronological_splits_do_not_overlap():
    p=split(data()); assert p["train"].observation_date.max()<p["validation"].observation_date.min()<p["test"].observation_date.min()
def test_at_risk_population_has_no_prior_negative_event():
    d=data(); assert (d.event_date.isna() | (d.observation_date<d.event_date)).all()

