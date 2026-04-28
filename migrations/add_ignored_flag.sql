-- Add ignored flag to job_offers
ALTER TABLE job_offers ADD COLUMN ignored BOOLEAN DEFAULT FALSE NOT NULL;
CREATE INDEX idx_job_offers_ignored ON job_offers(ignored);
