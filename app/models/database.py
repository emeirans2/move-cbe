from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                meta_ad_account_id VARCHAR(100),
                token_ref VARCHAR(500),
                geo VARCHAR(10) DEFAULT 'LV',
                daily_spend_cap_eur FLOAT DEFAULT 100.0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS creatives (
                id SERIAL PRIMARY KEY,
                client_id INTEGER REFERENCES clients(id),
                meta_ad_id VARCHAR(100),
                primary_text TEXT,
                headline VARCHAR(500),
                visual_description TEXT,
                status VARCHAR(50) DEFAULT 'active',
                vector vector(10),
                raw_scores JSONB,
                scored_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_context (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                geo VARCHAR(10) DEFAULT 'LV',
                brief TEXT,
                mood_vector vector(10),
                demand_index FLOAT DEFAULT 1.0,
                raw JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS matches (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                client_id INTEGER REFERENCES clients(id),
                creative_id INTEGER REFERENCES creatives(id),
                emotional_match FLOAT,
                demand_index FLOAT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id SERIAL PRIMARY KEY,
                match_id INTEGER REFERENCES matches(id),
                action_type VARCHAR(50),
                current_budget_eur FLOAT,
                proposed_budget_eur FLOAT,
                status VARCHAR(50) DEFAULT 'pending',
                guardrail_notes TEXT,
                decided_by VARCHAR(100),
                decided_at TIMESTAMP,
                executed_at TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP DEFAULT NOW(),
                event_type VARCHAR(100),
                entity_type VARCHAR(100),
                entity_id INTEGER,
                context JSONB
            )
        """))
        conn.commit()
    print("DB initialised successfully")
