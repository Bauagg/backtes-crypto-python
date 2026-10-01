from src.services.signal_trading import service
from src.services.signal_trading.schemas import SignalRequest


def get_signal(req: SignalRequest):
    """Sinyal entry harian: strategi dipilih dari modal (BTC-60 / V2-60), target porsi tiap coin,
    dan -- kalau `posisi` dikirim -- daftar order yang harus dijalankan backend Rust."""
    return service.get_signal(req)
