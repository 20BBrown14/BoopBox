"""OTA firmware index + ESP-Web-Tools manifest generator and cache.

The server reads built `.bin` files from a server-side firmware directory
(`BOOPBOX_FIRMWARE_DIR`) and exposes two views of one cached build:

- the ESP-Web-Tools `manifest.json` (browser provisioning over USB), and
- an internal firmware index (chip -> version/path/md5) that the push-command
  builder consults.

`version` comes only from `ota.manifest_version`; md5 is computed from the bin
bytes on disk. The build is cached and recomputed only when a relevant bin's
mtime changes.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CHIP_FAMILIES: dict[str, str] = {
    "esp32s3": "ESP32-S3",
}

MANIFEST_NAME = "BoopBox"


def bin_filename(version: str) -> str:
    """The bin filename convention for a version: boopbox-<version>.bin."""
    return f"boopbox-{version}.bin"


def served_path(chip: str, version: str) -> str:
    """Absolute, non-redirecting served path for a chip's bin at a version."""
    return f"/firmware/{chip}/{bin_filename(version)}"


@dataclass(frozen=True)
class IndexEntry:
    version: str
    path: str
    md5: str


def _md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scan(firmware_dir: Path, version: str) -> dict[str, Path]:
    """Map each known chip subfolder holding the versioned bin to that bin path.

    Chip dirs without the versioned bin are skipped (logged). Subfolders not in
    CHIP_FAMILIES are skipped (logged). Never raises on a missing dir.
    """
    found: dict[str, Path] = {}
    if not firmware_dir.is_dir():
        logger.warning("firmware dir does not exist: %s", firmware_dir)
        return found
    for child in sorted(firmware_dir.iterdir()):
        if not child.is_dir():
            continue
        chip = child.name
        if chip not in CHIP_FAMILIES:
            logger.info("skipping unknown firmware chip subfolder: %s", chip)
            continue
        bin_path = child / bin_filename(version)
        if not bin_path.is_file():
            logger.warning(
                "chip %s has no bin at version %s (%s)", chip, version, bin_path
            )
            continue
        found[chip] = bin_path
    return found


class FirmwareCache:
    """Cached firmware build: manifest JSON + index, with mtime invalidation.

    Built at startup and on config reload via `rebuild()`. On each read the
    relevant bins are stat'd cheaply; the build is recomputed only when a bin is
    added, removed, or changed (mtime drift). md5 is not recomputed otherwise.
    """

    def __init__(self, firmware_dir: str | Path, version: str) -> None:
        self._dir = Path(firmware_dir)
        self._version = version
        self._manifest: dict = {}
        self._index: dict[str, IndexEntry] = {}
        # chip -> mtime_ns the current build was computed from
        self._mtimes: dict[str, int] = {}
        self.rebuild()

    @property
    def version(self) -> str:
        return self._version

    def _current_mtimes(self, bins: dict[str, Path]) -> dict[str, int]:
        return {chip: path.stat().st_mtime_ns for chip, path in bins.items()}

    def rebuild(self) -> None:
        """Unconditionally rescan disk and rebuild the manifest + index."""
        bins = _scan(self._dir, self._version)
        builds = []
        index: dict[str, IndexEntry] = {}
        mtimes: dict[str, int] = {}
        for chip, path in bins.items():
            md5 = _md5_of(path)
            served = served_path(chip, self._version)
            builds.append(
                {
                    "chipFamily": CHIP_FAMILIES[chip],
                    "ota": {
                        "md5": md5,
                        "path": served,
                        "summary": "",
                        "release_url": "",
                    },
                }
            )
            index[chip] = IndexEntry(version=self._version, path=served, md5=md5)
            mtimes[chip] = path.stat().st_mtime_ns

        if not builds:
            logger.warning(
                "no firmware bins at version %s under %s; serving empty manifest",
                self._version,
                self._dir,
            )

        self._manifest = {
            "name": MANIFEST_NAME,
            "version": self._version,
            "builds": builds,
        }
        self._index = index
        self._mtimes = mtimes

    def _refresh_if_stale(self) -> None:
        """Rebuild only if the on-disk bin set or any bin's mtime has changed."""
        bins = _scan(self._dir, self._version)
        if self._current_mtimes(bins) != self._mtimes:
            self.rebuild()

    def manifest(self) -> dict:
        """The cached manifest dict, refreshed on bin mtime drift."""
        self._refresh_if_stale()
        return self._manifest

    def index(self, chip: str) -> IndexEntry | None:
        """Lookup an index entry for a chip, refreshed on bin mtime drift.

        Returns None for a chip without a bin at the configured version.
        """
        self._refresh_if_stale()
        return self._index.get(chip)
