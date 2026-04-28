import psycopg2
from psycopg2.extras import execute_batch
from typing import List
import logging

from scraper.models.job_offer import JobOffer
from scraper.config.settings import DB_CONFIG

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL connections and job offer persistence."""

    def __init__(self):
        """Initialize database manager with centralized config."""
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish a connection to PostgreSQL."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor()
            logger.info(
                f"Connected to PostgreSQL: {DB_CONFIG['user']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
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

            # Apply migrations for future columns
            self._add_column_if_not_exists('applied', 'BOOLEAN DEFAULT FALSE')
            self._add_column_if_not_exists('last_seen_at', 'TIMESTAMP DEFAULT NOW()')
            self._add_column_if_not_exists('is_active', 'BOOLEAN DEFAULT TRUE')
            # AI scoring columns
            self._add_column_if_not_exists('ai_score', 'FLOAT')
            self._add_column_if_not_exists('ai_recommendation', 'TEXT')
            self._add_column_if_not_exists('ai_analysis', 'TEXT')
            self._add_column_if_not_exists('scored_at', 'TIMESTAMP')
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to create table: {e}")
            raise

    def _add_column_if_not_exists(self, column_name: str, column_type: str):
        """
        Add a column to job_offers table if it doesn't already exist.

        Useful for future migrations (applied, last_seen_at, is_active, etc.)
        """
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

    def upsert_job_offers(self, job_offers: List[JobOffer]) -> int:
        """
        Insert job offers into the database, updating existing ones (by URL).

        Args:
            job_offers: List of JobOffer objects

        Returns:
            Number of offers upserted
        """
        if not job_offers:
            logger.info("No job offers to upsert")
            return 0

        upsert_query = """
        INSERT INTO job_offers
        (title, url, company, location, employment_type, remote_work, source, new_offer, salary, description, date_posted)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO UPDATE SET
            title = EXCLUDED.title,
            company = EXCLUDED.company,
            location = EXCLUDED.location,
            employment_type = EXCLUDED.employment_type,
            remote_work = EXCLUDED.remote_work,
            salary = EXCLUDED.salary,
            description = EXCLUDED.description,
            date_posted = EXCLUDED.date_posted;
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
            execute_batch(self.cursor, upsert_query, data, page_size=100)
            self.conn.commit()
            upserted_count = self.cursor.rowcount
            logger.info(f"Upserted {upserted_count} job offers into database")
            return upserted_count
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to upsert job offers: {e}")
            raise

    def mark_applied(self, url: str) -> bool:
        """
        Mark a job offer as applied.

        Args:
            url: URL of the offer to mark as applied

        Returns:
            True if the offer was updated, False if not found
        """
        try:
            query = "UPDATE job_offers SET applied = True WHERE url = %s;"
            self.cursor.execute(query, (url,))
            self.conn.commit()
            updated = self.cursor.rowcount > 0
            if updated:
                logger.info(f"Marked offer as applied: {url}")
            else:
                logger.warning(f"Offer not found: {url}")
            return updated
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to mark offer as applied: {e}")
            return False

    def mark_ignored(self, identifier, is_id: bool) -> tuple[bool, str]:
        """Mark an offer as ignored. Returns (success, title)."""
        try:
            if is_id:
                self.cursor.execute(
                    "UPDATE job_offers SET ignored = TRUE WHERE id = %s RETURNING title;",
                    (identifier,)
                )
            else:
                self.cursor.execute(
                    "UPDATE job_offers SET ignored = TRUE WHERE url = %s RETURNING title;",
                    (identifier,)
                )
            row = self.cursor.fetchone()
            if row:
                self.conn.commit()
                return True, row[0]
            else:
                self.conn.rollback()
                return False, ""
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to mark offer as ignored: {e}")
            return False, ""

    def update_last_seen(self, urls: List[str]) -> int:
        """
        Update last_seen_at to NOW() for all given URLs.

        Args:
            urls: List of URLs to update

        Returns:
            Number of offers updated
        """
        if not urls:
            return 0

        try:
            # Build query with placeholders for each URL
            placeholders = ",".join(["%s"] * len(urls))
            query = f"UPDATE job_offers SET last_seen_at = NOW() WHERE url IN ({placeholders});"
            self.cursor.execute(query, urls)
            self.conn.commit()
            updated_count = self.cursor.rowcount
            logger.info(f"Updated last_seen_at for {updated_count} offers")
            return updated_count
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to update last_seen_at: {e}")
            return 0

    def mark_inactive_if_unseen(self, days: int = 7) -> int:
        """
        Mark offers as inactive if not seen in the last N days.

        Args:
            days: Number of days threshold (default: 7)

        Returns:
            Number of offers marked as inactive
        """
        try:
            query = f"""
            UPDATE job_offers
            SET is_active = False
            WHERE is_active = True AND last_seen_at < NOW() - INTERVAL '{days} days';
            """
            self.cursor.execute(query)
            self.conn.commit()
            inactive_count = self.cursor.rowcount
            if inactive_count > 0:
                logger.info(f"Marked {inactive_count} offers as inactive (not seen in {days} days)")
            return inactive_count
        except psycopg2.Error as e:
            self.conn.rollback()
            logger.error(f"Failed to mark offers as inactive: {e}")
            return 0
