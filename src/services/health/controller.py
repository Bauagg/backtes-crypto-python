from src.databases import ping


def health():
    try:
        ping()
        db = "connected"
    except Exception:
        db = "disconnected"
    return {"status": "ok" if db == "connected" else "degraded", "database": db, "data_source": "database"}
