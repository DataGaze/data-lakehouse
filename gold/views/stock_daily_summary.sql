-- View: Daily market summary
-- Usage: SELECT * FROM stock_daily_summary WHERE date = '2026-03-20';

CREATE OR REPLACE VIEW stock_daily_summary AS
SELECT
    d.date,
    d.exchange,
    COUNT(*) AS total_symbols,
    SUM(CASE WHEN d.close > d.open THEN 1 ELSE 0 END) AS advancing,
    SUM(CASE WHEN d.close < d.open THEN 1 ELSE 0 END) AS declining,
    SUM(CASE WHEN d.close = d.open THEN 1 ELSE 0 END) AS unchanged,
    SUM(d.volume) AS total_volume,
    SUM(d.value) AS total_value
FROM daily_ohlcv d
GROUP BY d.date, d.exchange
ORDER BY d.date DESC, d.exchange;
