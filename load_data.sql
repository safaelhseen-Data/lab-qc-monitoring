-- Loads specs.csv and lab_qc_data.csv into the schema.
-- Run from the folder that contains the CSV files:
--   psql -d lab_qc -f load_data.sql

BEGIN;

TRUNCATE results, samples, tests RESTART IDENTITY CASCADE;

\copy tests (test_code, unit, min_limit, max_limit, method) FROM 'specs.csv' WITH (FORMAT csv, HEADER true)

-- The CSV is "wide" (one column per test), so load it into a staging table first
CREATE TEMP TABLE stg (
    sample_id   text,
    sample_date date,
    product     text,
    batch       text,
    analyst     text,
    density     numeric,
    viscosity   numeric,
    flash_point numeric,
    water_ppm   numeric,
    sulfur_ppm  numeric,
    status      text
) ON COMMIT DROP;

\copy stg FROM 'lab_qc_data.csv' WITH (FORMAT csv, HEADER true)

INSERT INTO samples (sample_id, sample_date, product, batch, analyst)
SELECT sample_id, sample_date, product, batch, analyst FROM stg;

-- Unpivot: one row per (sample, test)
INSERT INTO results (sample_id, test_code, value)
SELECT s.sample_id, v.test_code, v.value
FROM stg s
CROSS JOIN LATERAL (VALUES
    ('density',     s.density),
    ('viscosity',   s.viscosity),
    ('flash_point', s.flash_point),
    ('water_ppm',   s.water_ppm),
    ('sulfur_ppm',  s.sulfur_ppm)
) AS v (test_code, value);

COMMIT;
