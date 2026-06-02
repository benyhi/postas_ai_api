import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.billing.seed import seed_billing_catalog
from app.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as db:
        result = seed_billing_catalog(db)
    print(
        "Billing seed aplicado: "
        f"{result.plans} planes, {result.features} features, "
        f"{result.plan_features} configuraciones plan-feature."
    )


if __name__ == "__main__":
    main()
