"""
File management for PDF storage with hierarchical organization.

Provides functions for:
- Resolving storage paths based on collection hierarchy
- Saving PDFs to organized directory structure
- Checking file existence
- Listing stored files
- Calculating storage statistics
"""

import os
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .schemas import Collection, Sentence


class FileManager:
    """Manages hierarchical file storage for PDF documents."""

    def __init__(self, base_dir: Path):
        """
        Initialize file manager with base storage directory.

        Args:
            base_dir: Root directory for all stored files
        """
        self.base_dir = Path(base_dir).expanduser().resolve()
        self._ensure_base_dir()

    def _ensure_base_dir(self) -> None:
        """Create base storage directory if it doesn't exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _collection_path(self, collection: Collection) -> Path:
        """
        Resolve the directory path for a collection.

        Hierarchy: {base_dir}/{collection.org_code}/{collection.collection_code}

        Args:
            collection: Collection record

        Returns:
            Path to collection directory
        """
        org_code = collection.org_code or "unknown"
        coll_code = collection.collection_code or "unknown"
        return self.base_dir / org_code / coll_code

    def _sentence_filename(self, sentence: Sentence) -> str:
        """
        Generate filename for a sentence PDF.

        Uses sentence number with padded zeros and .pdf extension.

        Args:
            sentence: Sentence record

        Returns:
            Filename string
        """
        # Pad sentence number to 6 digits for sorting
        padded_num = str(sentence.sentence_number).zfill(6)
        return f"{padded_num}.pdf"

    def _sentence_path(self, sentence: Sentence, collection: Collection) -> Path:
        """
        Resolve full path for a sentence PDF file.

        Args:
            sentence: Sentence record
            collection: Parent collection record

        Returns:
            Full Path to PDF file
        """
        coll_path = self._collection_path(collection)
        filename = self._sentence_filename(sentence)
        return coll_path / filename

    def get_collection_dir(self, collection: Collection) -> Path:
        """
        Get or create the storage directory for a collection.

        Args:
            collection: Collection record

        Returns:
            Path to collection directory (created if needed)
        """
        path = self._collection_path(collection)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_pdf(
        self,
        pdf_data: bytes,
        sentence: Sentence,
        collection: Collection,
        overwrite: bool = False
    ) -> Path:
        """
        Save a PDF file to storage.

        Args:
            pdf_data: Raw PDF file bytes
            sentence: Sentence record (must have sentence_number)
            collection: Parent collection record
            overwrite: Whether to overwrite existing file

        Returns:
            Path to saved file

        Raises:
            FileExistsError: If file exists and overwrite=False
            ValueError: If sentence_number is None
        """
        if sentence.sentence_number is None:
            raise ValueError("sentence_number is required to generate filename")

        file_path = self._sentence_path(sentence, collection)

        if file_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {file_path}")

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file atomically
        temp_path = file_path.with_suffix('.pdf.tmp')
        with open(temp_path, 'wb') as f:
            f.write(pdf_data)
        temp_path.rename(file_path)

        return file_path

    def file_exists(self, sentence: Sentence, collection: Collection) -> bool:
        """
        Check if a sentence PDF file exists in storage.

        Args:
            sentence: Sentence record
            collection: Parent collection record

        Returns:
            True if file exists, False otherwise
        """
        if sentence.sentence_number is None:
            return False
        file_path = self._sentence_path(sentence, collection)
        return file_path.exists()

    def delete_file(self, sentence: Sentence, collection: Collection) -> bool:
        """
        Delete a sentence PDF file from storage.

        Args:
            sentence: Sentence record
            collection: Parent collection record

        Returns:
            True if file was deleted, False if not found
        """
        if sentence.sentence_number is None:
            return False
        file_path = self._sentence_path(sentence, collection)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_collection_files(self, collection: Collection) -> List[Path]:
        """
        List all PDF files in a collection directory.

        Args:
            collection: Collection record

        Returns:
            List of Path objects for PDF files (sorted by name)
        """
        coll_path = self._collection_path(collection)
        if not coll_path.exists():
            return []
        # Only include .pdf files, sorted naturally
        files = sorted(coll_path.glob('*.pdf'))
        return files

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Calculate storage statistics across all collections.

        Returns:
            Dictionary with:
                - total_size_bytes: Total storage used
                - total_files: Total number of PDF files
                - collections: Count of collection directories
                - base_dir: Storage base path
        """
        stats = {
            'total_size_bytes': 0,
            'total_files': 0,
            'collections': 0,
            'base_dir': str(self.base_dir)
        }

        # Walk through all subdirectories
        for org_dir in self.base_dir.iterdir():
            if not org_dir.is_dir():
                continue
            for coll_dir in org_dir.iterdir():
                if not coll_dir.is_dir():
                    continue
                stats['collections'] += 1
                for pdf_file in coll_dir.glob('*.pdf'):
                    if pdf_file.is_file():
                        stats['total_files'] += 1
                        stats['total_size_bytes'] += pdf_file.stat().st_size

        return stats

    def verify_file_integrity(
        self,
        sentence: Sentence,
        collection: Collection,
        expected_hash: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify integrity of a stored PDF file.

        Args:
            sentence: Sentence record
            collection: Parent collection record
            expected_hash: Optional SHA256 hex digest to compare

        Returns:
            Dictionary with:
                - exists: bool
                - size_bytes: int (0 if not exists)
                - sha256: str (empty if not exists)
                - matches_hash: bool (True if hash matches or not provided)
        """
        if sentence.sentence_number is None:
            return {
                'exists': False,
                'size_bytes': 0,
                'sha256': '',
                'matches_hash': False
            }

        file_path = self._sentence_path(sentence, collection)
        result = {
            'exists': False,
            'size_bytes': 0,
            'sha256': '',
            'matches_hash': False
        }

        if not file_path.exists():
            return result

        result['exists'] = True
        result['size_bytes'] = file_path.stat().st_size

        # Calculate SHA256
       sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256_hash.update(chunk)
        result['sha256'] = sha256_hash.hexdigest()

        if expected_hash:
            result['matches_hash'] = (result['sha256'] == expected_hash)
        else:
            result['matches_hash'] = True

        return result

    def migrate_to_hierarchical(
        self,
        old_root: Path,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Migrate flat file structure to hierarchical organization.

        Assumes old structure: {old_root}/{sentence_number}.pdf
        New structure: {base_dir}/{org_code}/{collection_code}/{sentence_number}.pdf

        Args:
            old_root: Path to old flat file directory
            dry_run: If True, only report what would be done

        Returns:
            Migration statistics
        """
        old_root = Path(old_root).expanduser().resolve()
        stats = {
            'scanned': 0,
            'moved': 0,
            'skipped': 0,
            'errors': []
        }

        if not old_root.exists():
            stats['errors'].append(f"Old root directory does not exist: {old_root}")
            return stats

        # Scan for PDF files
        for pdf_file in old_root.glob('*.pdf'):
            if not pdf_file.is_file():
                continue
            stats['scanned'] += 1

            # Extract sentence number from filename (assumes format: 000001.pdf)
            try:
                sentence_number = int(pdf_file.stem)
            except ValueError:
                stats['skipped'] += 1
                stats['errors'].append(f"Invalid filename format: {pdf_file.name}")
                continue

            # Determine target path (will need collection info from database)
            # This is a placeholder - actual migration requires database lookup
            # to determine org_code and collection_code
            target_path = self.base_dir / "migrated" / pdf_file.name
            target_path.parent.mkdir(parents=True, exist_ok=True)

            if not dry_run:
                try:
                    pdf_file.rename(target_path)
                    stats['moved'] += 1
                except Exception as e:
                    stats['errors'].append(f"Failed to move {pdf_file.name}: {e}")
            else:
                stats['moved'] += 1  # Count hypothetical moves

        return stats
