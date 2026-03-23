-- View: Latest stock prices (most recent trading day)
-- Usage: SELECT * FROM stock_latest_prices WHERE exchange = 'HOSE';

CREATE OR REPLACE VIEW stock_latest_prices AS
SELECT
    d.symbol,
    d.exchange,
    d.date,
    d.open,
    d.high,
    d.low,
    d.close,
    d.volume,
    d.value,
    d.close - LAG(d.close) OVER (PARTITION BY d.symbol ORDER BY d.date) AS change,
    ROUND(
        (d.close - LAG(d.close) OVER (PARTITION BY d.symbol ORDER BY d.date))
        / NULLIF(LAG(d.close) OVER (PARTITION BY d.symbol ORDER BY d.date), 0) * 100,
        2
    ) AS change_pct
FROM daily_ohlcv d
WHERE d.date >= CURRENT_DATE - INTERVAL '5 days';
