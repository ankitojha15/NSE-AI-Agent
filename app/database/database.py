from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base


DATABASE_URL = "mysql+pymysql://root:12%40root12@localhost:3306/nse_ai"
engine = create_engine(
    DATABASE_URL
)

SessionLocal = sessionmaker(
    autocommit = False,
    autoflush = False,
    bind=engine
)

from app.models.company import Company

Base.metadata.create_all(bind=engine)