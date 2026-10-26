-- =====================================================
-- Lab QC Database (Diesel fuel testing)
-- PostgreSQL 14+
-- =====================================================

DROP VIEW  IF EXISTS v_test_summary;
DROP VIEW  IF EXISTS v_out_of_spec;
DROP VIEW  IF EXISTS v_results_checked;
DROP TABLE IF EXISTS results;
DROP TABLE IF EXISTS samples;
DROP TABLE IF EXISTS tests;

-- Specification limits per test (one row per test method)
CREATE TABLE tests (
    test_code  text    PRIMARY KEY,          -- density, viscosity, ...
    unit       text    NOT NULL,
    min_limit  numeric,                      -- NULL = no lower limit
    max_limit  numeric,                      -- NULL = no upper limit
    method     text    NOT NULL,             -- e.g. ASTM D4052
    CONSTRAINT at_least_one_limit CHECK (min_limit IS NOT NULL OR max_limit IS NOT NULL),
    CONSTRAINT limits_order CHECK (min_limit IS NULL OR max_limit IS NULL OR min_limit < max_limit)
);

-- One row per physical sample
CREATE TABLE samples (
    sample_id    text  PRIMARY KEY,
    sample_date  date  NOT NULL,
    product      text  NOT NULL,
    batch        text  NOT NULL,
    analyst      text  NOT NULL
);

-- One row per (sample, test) measurement. NULL value = missing result.
CREATE TABLE results (
    result_id  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sample_id  text    NOT NULL REFERENCES samples (sample_id) ON DELETE CASCADE,
    test_code  text    NOT NULL REFERENCES tests (test_code),
    value      numeric,
    CONSTRAINT one_result_per_test UNIQUE (sample_id, test_code)
);

CREATE INDEX idx_samples_date    ON samples (sample_date);
CREATE INDEX idx_samples_batch   ON samples (batch);
CREATE INDEX idx_results_test    ON results (test_code, sample_id);

-- Every result joined with its sample info, limits and a status flag
CREATE VIEW v_results_checked AS
SELECT
    r.result_id,
    s.sample_id,
    s.sample_date,
    s.batch,
    s.analyst,
    r.test_code,
    r.value,
    t.unit,
    t.min_limit,
    t.max_limit,
    CASE
        WHEN r.value IS NULL THEN 'MISSING'
        WHEN (t.min_limit IS NOT NULL AND r.value < t.min_limit)
          OR (t.max_limit IS NOT NULL AND r.value > t.max_limit) THEN 'OUT_OF_SPEC'
        ELSE 'OK'
    END AS status
FROM results r
JOIN samples s USING (sample_id)
JOIN tests   t USING (test_code);

-- Only the failing results
CREATE VIEW v_out_of_spec AS
SELECT * FROM v_results_checked WHERE status = 'OUT_OF_SPEC';

-- Per-test summary statistics (starting point for control charts)
CREATE VIEW v_test_summary AS
SELECT
    test_code,
    count(*)                                   AS n_total,
    count(value)                               AS n_measured,
    count(*) - count(value)                    AS n_missing,
    round(avg(value), 3)                       AS mean,
    round(stddev_samp(value), 3)               AS std_dev,
    min(value)                                 AS min_value,
    max(value)                                 AS max_value,
    count(*) FILTER (WHERE status = 'OUT_OF_SPEC') AS n_out_of_spec
FROM v_results_checked
GROUP BY test_code;
