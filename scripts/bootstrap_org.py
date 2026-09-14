import argparse

from app.db import Base, SessionLocal, engine
from app.models import Organization
from app.presets import PRESETS
from app.security import hash_api_key, new_org_api_key
from app.services.profiles import replace_active_profile

def main():
    parser = argparse.ArgumentParser(description="Create a local organization and print its API key once.")
    parser.add_argument("name")
    parser.add_argument("--preset", choices=PRESETS.keys(), default="custom")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    raw_key = new_org_api_key()
    db = SessionLocal()
    try:
        org = Organization(name=args.name, industry=args.preset, api_key_hash=hash_api_key(raw_key))
        db.add(org)
        db.commit()
        db.refresh(org)
        preset = PRESETS[args.preset]
        replace_active_profile(db, org.id, preset["name"], preset)
        print(f"Organization: {org.name}")
        print(f"Organization ID: {org.id}")
        print(f"API key (save this now): {raw_key}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
