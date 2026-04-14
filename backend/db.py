import sqlite3
import json
from datetime import datetime

DB_PATH = "./halos.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            filename TEXT,
            created_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            batch_id TEXT,
            job_id TEXT,
            filename TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            timestamp TEXT,
            seconds INTEGER,
            label TEXT,
            description TEXT,
            embedding TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def save_job(job_id: str, filename: str):
    conn = get_connection()
    cursor = conn.cursor()
    created_at = datetime.utcnow().isoformat() + "Z"
    cursor.execute(
        "INSERT OR IGNORE INTO jobs (job_id, filename, created_at) VALUES (?, ?, ?)",
        (job_id, filename, created_at)
    )
    conn.commit()
    conn.close()

def save_events(job_id: str, events: list) -> list[int]:
    conn = get_connection()
    cursor = conn.cursor()
    inserted_ids = []
    for event in events:
        cursor.execute(
            "INSERT INTO events (job_id, timestamp, seconds, label, description) VALUES (?, ?, ?, ?, ?)",
            (job_id, event.get("timestamp"), event.get("seconds"), event.get("label"), event.get("description"))
        )
        inserted_ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    return inserted_ids

def save_embedding(event_id: int, embedding: list[float]):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE events SET embedding = ? WHERE id = ?",
        (json.dumps(embedding), event_id)
    )
    conn.commit()
    conn.close()

def save_batch(batch_id: str, job_id: str, filename: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO batches (batch_id, job_id, filename) VALUES (?, ?, ?)",
        (batch_id, job_id, filename)
    )
    conn.commit()
    conn.close()

def get_jobs_in_batch(batch_id: str) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT job_id, filename FROM batches WHERE batch_id = ?", (batch_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_events_with_embeddings() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, job_id, timestamp, seconds, label, description, embedding FROM events WHERE embedding IS NOT NULL"
    )
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        d = dict(row)
        if d["embedding"]:
            d["embedding"] = json.loads(d["embedding"])
        results.append(d)
    return results

def get_filename_for_job(job_id: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM jobs WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return row["filename"] if row else ""
