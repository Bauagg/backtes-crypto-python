from src.services.recommendation.service import is_model_loaded, peek_snapshot


def health():
    snapshot = peek_snapshot()
    return {"status": "ok",
            "coins_loaded": len(snapshot.coin_dfs) if snapshot else 0,
            "model_loaded": is_model_loaded(),
            "data_source": "database"}
