//! Contoh klien Rust untuk memanggil Crypto Strategy V5 API.
//!
//! Tambahkan di Cargo.toml:
//!   reqwest = { version = "0.12", features = ["json"] }
//!   serde   = { version = "1", features = ["derive"] }
//!   tokio   = { version = "1", features = ["full"] }
//!
//! Jalankan API dulu:  python -m uvicorn api:app --port 8000

use serde::{Deserialize, Serialize};

const API_BASE: &str = "http://localhost:8000";

// ===== Skema respons =====

#[derive(Debug, Deserialize)]
struct Health {
    status: String,
    coins_loaded: u32,
    model_loaded: bool,
}

#[derive(Debug, Deserialize)]
struct Coin {
    symbol: String,
    correlation_to_btc: f64,
    tradeable: bool,
}

#[derive(Debug, Deserialize)]
struct CoinsResponse {
    symbol_format: String,
    coins: Vec<Coin>,
    tradeable_count: u32,
    total: u32,
}

#[derive(Debug, Deserialize)]
struct Signal {
    symbol: String,
    verdict: String,               // "BUY" atau "SKIP"
    ml_confidence: Option<f64>,
    reason: String,
    #[serde(default)]
    close: f64,
}

#[derive(Debug, Deserialize)]
struct ScanResponse {
    date: String,
    buy_signals: Vec<Signal>,
    total_scanned: u32,
    buy_count: u32,
}

#[derive(Debug, Deserialize)]
struct BacktestResponse {
    period: String,
    n_trades: u32,
    win_rate: Option<f64>,
    initial_capital: f64,
    final_capital: f64,
    return_pct: f64,
}

// ===== Skema request =====

#[derive(Debug, Serialize)]
struct ScoreRequest<'a> {
    symbol: &'a str,   // format Tokocrypto: "BTCUSDT"
    date: &'a str,     // "YYYY-MM-DD"
}

#[derive(Debug, Serialize)]
struct ScanRequest<'a> {
    date: Option<&'a str>,
    only_tradeable: bool,
}

#[derive(Debug, Serialize)]
struct BacktestRequest<'a> {
    start: &'a str,
    end: &'a str,
    initial_capital: f64,
    position_fraction: f64,
    only_tradeable: bool,
}

// ===== Fungsi klien =====

async fn health(client: &reqwest::Client) -> reqwest::Result<Health> {
    client.get(format!("{API_BASE}/health")).send().await?.json().await
}

async fn get_coins(client: &reqwest::Client) -> reqwest::Result<CoinsResponse> {
    client.get(format!("{API_BASE}/coins")).send().await?.json().await
}

async fn score(client: &reqwest::Client, symbol: &str, date: &str) -> reqwest::Result<Signal> {
    client.post(format!("{API_BASE}/score"))
        .json(&ScoreRequest { symbol, date })
        .send().await?.json().await
}

async fn scan(client: &reqwest::Client, date: Option<&str>) -> reqwest::Result<ScanResponse> {
    client.post(format!("{API_BASE}/scan"))
        .json(&ScanRequest { date, only_tradeable: true })
        .send().await?.json().await
}

async fn backtest(client: &reqwest::Client, start: &str, end: &str) -> reqwest::Result<BacktestResponse> {
    client.post(format!("{API_BASE}/backtest"))
        .json(&BacktestRequest {
            start, end, initial_capital: 1000.0,
            position_fraction: 0.20, only_tradeable: true,
        })
        .send().await?.json().await
}

// ===== Contoh alur pemakaian =====

#[tokio::main]
async fn main() -> reqwest::Result<()> {
    let client = reqwest::Client::new();

    // 1. Cek API hidup
    let h = health(&client).await?;
    println!("API: {} | {} coin | model={}", h.status, h.coins_loaded, h.model_loaded);

    // 2. Ambil daftar coin tradeable (sekali saat startup)
    let coins = get_coins(&client).await?;
    println!("\nCoin tradeable ({}/{}):", coins.tradeable_count, coins.total);
    for c in coins.coins.iter().filter(|c| c.tradeable) {
        println!("  {} (korr {:.2})", c.symbol, c.correlation_to_btc);
    }

    // 3. Scan sinyal BUY hari terbaru
    let s = scan(&client, Some("2025-11-22")).await?;
    println!("\nSinyal BUY pada {}: {} dari {} coin", s.date, s.buy_count, s.total_scanned);
    for sig in &s.buy_signals {
        println!("  BUY {} conf={:.2} @ ${} — {}",
                 sig.symbol, sig.ml_confidence.unwrap_or(0.0), sig.close, sig.reason);
        // >>> Di sini backend Rust eksekusi order ke Tokocrypto <<<
    }

    // 4. Cek satu coin spesifik (Tokocrypto pakai BTCUSDT)
    let sig = score(&client, "BNBUSDT", "2025-11-22").await?;
    println!("\nScore BNBUSDT: {} — {}", sig.verdict, sig.reason);

    // 5. Backtest berkala untuk cek performa
    let bt = backtest(&client, "2024-01-01", "2026-06-30").await?;
    println!("\nBacktest {}: {} trade, win rate {:.1}%, ${:.0} -> ${:.0} ({:+.1}%)",
             bt.period, bt.n_trades, bt.win_rate.unwrap_or(0.0) * 100.0,
             bt.initial_capital, bt.final_capital, bt.return_pct * 100.0);

    Ok(())
}
