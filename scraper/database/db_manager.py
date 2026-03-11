import os
import psycopg2
from psycopg2.extras import execute_batch
from typing import List
import logging

from scraper.models.job_offer import JobOffer

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL connections and job offer persistence."""

    def __init__(self):
        """Initialize database connection parameters from environment variables."""
        self.host = os.getenv("DB_HOST", "localhost")
        self.port = int(os.getenv("DB_PORT", 5432))
        self.dbname = os.getenv("DB_NAME", "hellowork")
        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD", "")
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish a connection to PostgreSQL."""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.dbname,
                user=self.user,
                password=self.password,
            )
            self.cursor = self.conn.cursor()
            logger.info(
                f"Connected to PostgreSQL: {self.user}@{self.host}:{self.port}/{self.dbname}"
            )
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def close(self):
        """Close the database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from PostgreSQL")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def create_table(self):
        """Create the job_offers table if it doesn't exist."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS job_offers (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            company TEXT,
            location TEXT,
            employment_type TEXT,
            remote_work TEXT,
            source TEXT DEFAULT 'hellowork',
            new_offer BOOLEAN DEFAULT TRUE,
            salary TEXT,
            description TEXT,
            date_posted TEXT,
            scraped_at TIMESTAMP DEFAULT NOW()
        );
        """
        try:
            self.cursor.execute(create_table_query)
            self.conn.commit()
            logger.info("Ensured job_offers table exists")

            # Migration: add new_offer column if it doesn't exist
            self._add_column_if_not_exists('new_offer', 'BOOLEAN DEFAULT TRUE')
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to create table: {e}")
            raise

    def _add_column_if_not_exists(self, column_name: str, column_type: str):
        """Add a column to job_offers table if it doesn't already exist."""
        try:
            check_query = """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='job_offers' AND column_name=%s
            );
            """
            self.cursor.execute(check_query, (column_name,))
            column_exists = self.cursor.fetchone()[0]

            if not column_exists:
                alter_query = f"ALTER TABLE job_offers ADD COLUMN {column_name} {column_type};"
                self.cursor.execute(alter_query)
                self.conn.commit()
                logger.info(f"Added column '{column_name}' to job_offers table")
            else:
                logger.debug(f"Column '{column_name}' already exists in job_offers table")
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.warning(f"Could not add column '{column_name}': {e}")

    def get_existing_urls(self, urls: List[str]) -> set:
        """
        Get a set of URLs that already exist in the database.

        Args:
            urls: List of URLs to check

        Returns:
            Set of URLs that exist in the database
        """
        if not urls:
            return set()

        try:
            # Build query with placeholders for each URL
            placeholders = ",".join(["%s"] * len(urls))
            query = f"SELECT url FROM job_offers WHERE url IN ({placeholders});"
            self.cursor.execute(query, urls)
            return {row[0] for row in self.cursor.fetchall()}
        except psycopg2.Error as e:
            logger.error(f"Failed to check existing URLs: {e}")
            return set()

    def mark_known_offers_not_new(self, urls: List[str]):
        """
        Mark existing offers as not new (new_offer = False).

        Args:
            urls: List of URLs to mark as known
        """
        if not urls:
            return

        try:
            # Build query with placeholders for each URL
            placeholders = ",".join(["%s"] * len(urls))
            query = f"UPDATE job_offers SET new_offer = False WHERE url IN ({placeholders});"
            self.cursor.execute(query, urls)
            self.conn.commit()
            logger.info(f"Marked {self.cursor.rowcount} offers as not new")
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to mark offers as not new: {e}")

    def insert_job_offers(self, job_offers: List[JobOffer]) -> int:
        """
        Insert job offers into the database, ignoring duplicates (by URL).

        Args:
            job_offers: List of JobOffer objects

        Returns:
            Number of offers inserted
        """
        if not job_offers:
            logger.info("No job offers to insert")
            return 0

        insert_query = """
        INSERT INTO job_offers
        (title, url, company, location, employment_type, remote_work, source, new_offer, salary, description, date_posted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO NOTHING;
        """

        data = [
            (
                offer.title,
                offer.url,
                offer.company,
                offer.location,
                offer.employment_type.value,
                offer.remote_work.value,
                offer.source,
                offer.new_offer,
                offer.salary,
                offer.description,
                offer.date_posted,
            )
            for offer in job_offers
        ]

        try:
            execute_batch(self.cursor, insert_query, data, page_size=100)
            self.conn.commit()
            inserted_count = self.cursor.rowcount
            logger.info(f"Inserted {inserted_count} job offers into database")
            return inserted_count
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to insert job offers: {e}")
            raise
