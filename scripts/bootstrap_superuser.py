from app.config import settings
from app.db import Base, SessionLocal, engine
from app.services.superuser import ensure_local_superuser


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = ensure_local_superuser(db, force=True)
        if user is None:
            raise SystemExit("Superuser bootstrap settings are incomplete.")
        print(f"Superuser ready: {settings.bootstrap_superuser_username}")


if __name__ == "__main__":
    main()
