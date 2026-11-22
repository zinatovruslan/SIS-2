-- SQL verification queries for data/earthquakes.db
-- Run manually: sqlite3 data/earthquakes.db < sql/verification_queries.sql
-- The same checks are executed by: python -m src.loader --verify

-- 1. Number of stored rows (must equal the number of cleaned records)
SELECT COUNT(*) AS total_rows FROM earthquakes;

-- 2. Uniqueness: total rows and distinct ids must be equal (no duplicates)
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT id) AS distinct_ids FROM earthquakes;

-- 3. Top 5 strongest earthquakes
SELECT id, mag, place, time_utc FROM earthquakes ORDER BY mag DESC LIMIT 5;

-- 4. Events by depth band
SELECT depth_band, COUNT(*) AS events, ROUND(AVG(mag), 2) AS avg_mag
FROM earthquakes GROUP BY depth_band ORDER BY events DESC;

-- 5. Average magnitude by tsunami flag
SELECT tsunami, COUNT(*) AS events, ROUND(AVG(mag), 3) AS avg_mag
FROM earthquakes GROUP BY tsunami;

-- 6. Top 10 regions
SELECT region, COUNT(*) AS events FROM earthquakes
GROUP BY region ORDER BY events DESC LIMIT 10;

-- 7. Missing values in mandatory columns (must be 0)
SELECT COUNT(*) AS rows_with_nulls FROM earthquakes
WHERE mag IS NULL OR place IS NULL OR time_utc IS NULL OR latitude IS NULL OR longitude IS NULL;
