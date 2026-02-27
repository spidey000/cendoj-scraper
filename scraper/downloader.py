import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tenacity import retry, retry_if_exception_type, wait_random_exponential

from config.settings import Config
from scraper.models import Sentence
from utils.logger import get_logger
from utils.rate_limiter import RateLimiter


logger = get_logger(__name__)


@dataclass
class DownloadResult:
    sentence_id: str
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0


def retry_on_failure(max_attempts: int = 3, wait_min: float = 1, wait_max: float = 10):
    """Retry decorator for transient failures."""
    return retry(
        stop=lambda _: False,  # Never stop automatically, we handle attempts manually
        wait=wait_random_exponential(min=wait_min, max=wait_max),
        retry=retry_if_exception_type((IOError, OSError, ConnectionError)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry {retry_state.attempt_number}/{max_attempts} after error: {retry_state.outcome.exception()}"
        )
    )


class Downloader:
    def __init__(
        self,
        config: Config,
        browser_manager: Optional["BrowserManager"] = None
    ):
        self.config = config
        self.browser_manager = browser_manager
        self.rate_limiter = RateLimiter(rate=config.rate_limit)
        self.pdf_dir = Path(config.storage_config.get("pdf_dir", "data/pdfs"))
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = config.max_concurrent
        self.request_retries = config.request_retries
        self.chunk_size = config.chunk_size
        self.download_timeout = config.download_timeout

        # Track active downloads for concurrency control
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._active_downloads = set()

    def _get_file_path(self, sentence: Sentence) -> Path:
        """Generate deterministic file path for a sentence."""
        filename = f"{sentence.cendoj_number}.pdf"
        return self.pdf_dir / filename

    def _verify_checksum(self, file_path: Path, expected: Optional[str]) -> bool:
        """Verify SHA256 checksum of downloaded file."""
        if not expected:
            return True
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(self.chunk_size):
                sha256.update(chunk)
        computed = sha256.hexdigest()
        return computed == expected

    async def _download_file(self, sentence: Sentence, resume: bool = True) -> DownloadResult:
        """Core download implementation with retry logic."""
        async with self._semaphore:
            self._active_downloads.add(sentence.id)
            start_time = asyncio.get_event_loop().time()

            try:
                file_path = self._get_file_path(sentence)
                url = sentence.pdf_url

                # Check if already downloaded and valid
                if file_path.exists() and resume:
                    if self._verify_checksum(file_path, sentence.checksum):
                        logger.info(f"File already exists and valid: {file_path}")
                        return DownloadResult(
                            sentence_id=sentence.id,
                            success=True,
                            file_path=str(file_path),
                            duration=0.0
                        )
                    else:
                        logger.warning(f"Existing file invalid, will re-download: {file_path}")
                        file_path.unlink(missing_ok=True)

                # Apply rate limiting before starting
                await self.rate_limiter.wait()

                # Attempt download with retry
                attempt = 0
                while attempt < self.request_retries:
                    attempt += 1
                    try:
                        logger.info(f"Downloading {sentence.id} from {url} (attempt {attempt})")

                        # Use aiohttp for async HTTP download
                        import aiohttp
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.download_timeout)) as session:
                            headers = {"User-Agent": getattr(self.config, "user_agent", "Mozilla/5.0")}
                            async with session.get(url, headers=headers) as response:
                                response.raise_for_status()

                                # Get total size if available
                                total_size = int(response.headers.get("Content-Length", 0))
                                mode = "ab" if resume and file_path.exists() else "wb"
                                downloaded = file_path.stat().st_size if mode == "ab" else 0

                                # Stream to file
                                with open(file_path, mode) as f:
                                    async for chunk in response.content.iter_chunked(self.chunk_size):
                                        f.write(chunk)
                                        downloaded += len(chunk)
                                        if total_size:
                                            progress = downloaded / total_size * 100
                                            logger.debug(f"Progress: {progress:.1f}%")

                        logger.info(f"Downloaded {sentence.id} to {file_path}")

                        # Verify checksum if provided
                        if not self._verify_checksum(file_path, sentence.checksum):
                            raise IOError("Checksum verification failed")

                        # Update sentence object
                        sentence.file_path = str(file_path)
                        sentence.downloaded_at = asyncio.get_event_loop().time()

                        return DownloadResult(
                            sentence_id=sentence.id,
                            success=True,
                            file_path=str(file_path),
                            duration=asyncio.get_event_loop().time() - start_time
                        )

                    except Exception as e:
                        if attempt >= self.request_retries:
                            raise
                        logger.warning(f"Download failed (attempt {attempt}): {e}")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff

                raise RuntimeError("Max retries exceeded")

            except Exception as e:
                logger.error(f"Download failed for {sentence.id}: {e}")
                return DownloadResult(
                    sentence_id=sentence.id,
                    success=False,
                    error=str(e),
                    duration=asyncio.get_event_loop().time() - start_time
                )
            finally:
                self._active_downloads.discard(sentence.id)

    async def download(self, sentence: Sentence, resume: bool = True) -> DownloadResult:
        """Download a single sentence PDF with rate limiting and retry."""
        async with self.rate_limiter:
            return await self._download_file(sentence, resume)

    async def download_batch(self, sentences: list[Sentence]) -> list[DownloadResult]:
        """Download multiple sentences concurrently with rate limiting."""
        tasks = [self.download(sentence) for sentence in sentences]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return results
