"""Concurrent, recoverable acquisition with guarded NAS publication.

Source parsers are reused from Music Grabber; transfer, validation, tagging
and publication are app-owned. Preview/test storage remains isolated by default.
"""

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import time
import threading
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    TALB,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TRCK,
    TXXX,
)
from mutagen.mp4 import MP4, MP4FreeForm
from mutagen.flac import FLAC
from .soulseek import Soulseek

from .vendor.audio_probe import probe_file
from .vendor.freemp3cloud import search_freemp3cloud
from .vendor.zvu4no import search_zvu4no
from .vendor.jiosaavn import search_jiosaavn
from .quality import policy
from .storage import download_root, library_root

PROVIDERS = {
    "freemp3cloud": search_freemp3cloud,
    "zvu4no": search_zvu4no,
    "jiosaavn": search_jiosaavn,
}
PROFILES = {"mp3_320": 300, "mp3_128": 120, "aac_256": 240, "lossless": None}
VERSION_WORDS = {
    "live",
    "remix",
    "remaster",
    "remastered",
    "acoustic",
    "demo",
    "karaoke",
    "instrumental",
    "cover",
}


def folded(text):
    return " ".join(
        re.findall(
            r"\w+",
            "".join(
                c
                for c in unicodedata.normalize("NFKD", text or "").casefold()
                if not unicodedata.combining(c)
            ),
        )
    )


def duration(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        parts = [float(v) for v in str(value).split(":")]
        return sum(v * 60**i for i, v in enumerate(reversed(parts)))
    except ValueError:
        return 0


def matches(target, candidate):
    if folded(candidate.get("channel")) != folded(target["artist"]):
        return False
    if folded(candidate.get("title")) != folded(target["title"]):
        return False
    expected_versions = (
        set(folded(target["title"] + " " + target["album"]).split()) & VERSION_WORDS
    )
    actual_versions = (
        set(
            folded(
                candidate.get("title", "") + " " + candidate.get("album", "")
            ).split()
        )
        & VERSION_WORDS
    )
    if expected_versions != actual_versions:
        return False
    expected, actual = duration(target.get("duration")), duration(
        candidate.get("duration")
    )
    return actual > 0 and (not expected or abs(actual - expected) <= 5)


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:100] or "Unknown"
    if value.upper().split(".")[0] in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        value = "_" + value
    return value


# freemp3cloud silently returns empty pages when searched in parallel or too fast.
FREEMP3CLOUD_GAP = 2.5
FREEMP3CLOUD_RETRY_PAUSE = 10.0
_freemp3cloud_lock = threading.Lock()
_freemp3cloud_last = [0.0]


class Cancelled(Exception):
    pass


class QualityDeadline(Exception):
    pass


class Downloader:
    def __init__(self, store, providers=None):
        self.store = store
        self.providers = providers if providers is not None else PROVIDERS
        self.soulseek = Soulseek(store)
        self.stopping = asyncio.Event()
        self.deadlines = {}
        self.context = threading.local()
        configured = Path(
            os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT") or store.directory / "downloads"
        )
        self.library_root = configured / "library"
        self.staging = configured / "staging"
        (store.directory / "downloads" / "staging").mkdir(parents=True, exist_ok=True)
        try:
            self.prepare_storage()
        except (OSError, ValueError):
            pass  # Cached browsing and settings remain available without the NAS.

    def prepare_storage(self):
        download_root(self.store)  # Validate identity before creating any NAS path.
        self.library_root.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)

    def check(self, job_id):
        download_root(self.store)
        if self.stopping.is_set() or not self.store.request_active(
            job_id, getattr(self.context, "claim_token", None)
        ):
            raise Cancelled()
        if self.deadlines.get(job_id, float("inf")) <= time.monotonic():
            raise QualityDeadline()
        if not self.store.download_settings()["enabled"]:
            self.state(job_id, "waiting_for_sources")
            raise Cancelled()

    def pause(self, job_id, seconds):
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            self.check(job_id)
            time.sleep(min(0.5, left))

    def paced_search(self, job, query):
        search = self.providers["freemp3cloud"]
        for attempt in range(2):
            while not _freemp3cloud_lock.acquire(timeout=0.5):
                self.check(job["id"])
            try:
                self.check(job["id"])
                self.pause(
                    job["id"],
                    _freemp3cloud_last[0] + FREEMP3CLOUD_GAP - time.monotonic(),
                )
                try:
                    found = search(query, 20)
                finally:
                    _freemp3cloud_last[0] = time.monotonic()
            finally:
                _freemp3cloud_lock.release()
            if found or attempt:
                return found
            self.pause(job["id"], FREEMP3CLOUD_RETRY_PAUSE)
        return found

    def state(self, request_id, status, **details):
        self.store.request_state(
            request_id,
            status,
            _claim_token=getattr(self.context, "claim_token", None),
            **details,
        )

    async def run(self):
        recovered = False
        tasks = set()
        next_scan = 0
        try:
            while not self.stopping.is_set():
                try:
                    self.prepare_storage()
                except (OSError, ValueError):
                    try:
                        await asyncio.wait_for(self.stopping.wait(), timeout=5)
                    except TimeoutError:
                        pass
                    continue
                if not recovered:
                    self.store.recover_requests()
                    recovered = True
                tasks = {t for t in tasks if not t.done()}
                if time.monotonic() >= next_scan:
                    self.store.schedule_upgrades()
                    next_scan = time.monotonic() + 60
                limit = self.store.download_settings()["concurrent_downloads"]
                while len(tasks) < limit and not self.stopping.is_set():
                    job = self.store.claim_request()
                    if not job:
                        break
                    tasks.add(asyncio.create_task(asyncio.to_thread(self.process, job)))
                try:
                    await asyncio.wait_for(self.stopping.wait(), timeout=0.5)
                except TimeoutError:
                    pass
        finally:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    def transfer(self, job_id, candidate, path):
        source = candidate["source"]
        if source == "soulseek":
            return self.soulseek.transfer(
                candidate,
                path,
                lambda: self.check(job_id),
                lambda received, total: self.store.progress(job_id, received, total),
            )
        allowed = {
            "freemp3cloud": ("meln.top", "freemp3cloud.com"),
            "zvu4no": ("zvu4it.org",),
            "jiosaavn": ("saavncdn.com",),
        }[source]
        url = candidate["source_url"]
        started = time.monotonic()
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            for _ in range(5):
                parsed = urlsplit(url)
                host = parsed.hostname or ""
                if (
                    parsed.scheme != "https"
                    or parsed.port not in (None, 443)
                    or parsed.username
                    or not any(host == d or host.endswith("." + d) for d in allowed)
                ):
                    raise ValueError("Source returned an unsupported download address")
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = str(response.url.join(response.headers["location"]))
                        continue
                    response.raise_for_status()
                    expected = int(response.headers.get("content-length", 0))
                    if expected > 80_000_000:
                        raise ValueError(
                            "Source file exceeds the single-track size limit"
                        )
                    size = 0
                    with path.open("wb") as output:
                        for chunk in response.iter_bytes(65536):
                            self.check(job_id)
                            size += len(chunk)
                            if size > 80_000_000 or time.monotonic() - started > 180:
                                raise ValueError(
                                    "Transfer exceeded the track size/time limit"
                                )
                            output.write(chunk)
                            self.store.progress(
                                job_id,
                                size,
                                expected,
                                getattr(self.context, "claim_token", None),
                            )
                    if not size or expected and size != expected:
                        raise ValueError("Source delivered an incomplete file")
                    return
        raise ValueError("Source returned too many redirects")

    def validate(self, path, target, profile):
        probe = probe_file(path)
        expected_codec = (
            "flac"
            if profile == "lossless"
            else "aac" if profile == "aac_256" else "mp3"
        )
        if not probe or probe["codec"] != expected_codec:
            raise ValueError(
                f"Downloaded content is not readable {expected_codec.upper()} for this quality profile"
            )
        for key in ("artist", "title"):
            if probe.get(key) and folded(probe[key]) != folded(target[key]):
                raise ValueError(
                    "Embedded recording metadata does not match the request"
                )
        expected_versions = (
            set(folded(target["title"] + " " + target["album"]).split()) & VERSION_WORDS
        )
        actual_versions = (
            set(
                folded(
                    (probe.get("title") or "") + " " + (probe.get("album") or "")
                ).split()
            )
            & VERSION_WORDS
        )
        if actual_versions and actual_versions != expected_versions:
            raise ValueError("Embedded recording version does not match the request")
        minimum = PROFILES[profile]
        if minimum is not None and probe["bitrate_kbps"] < minimum:
            raise ValueError(
                "Downloaded audio does not meet the selected quality profile"
            )
        if target.get("duration") and abs(probe["duration"] - target["duration"]) > 5:
            raise ValueError("Downloaded recording has the wrong duration")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ValueError("FFmpeg is required to validate the complete recording")
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
            capture_output=True,
            timeout=90,
        )
        if result.returncode:
            raise ValueError("The downloaded audio failed complete decoding")
        return probe

    def tag(self, path, target, source):
        if path.suffix == ".flac":
            audio = FLAC(path)
            for field, key in (
                ("title", "TITLE"),
                ("artist", "ARTIST"),
                ("album", "ALBUM"),
                ("album_artist", "ALBUMARTIST"),
                ("disc_number", "DISCNUMBER"),
                ("track_number", "TRACKNUMBER"),
                ("year", "DATE"),
                ("musicbrainz_release_id", "MUSICBRAINZ_ALBUMID"),
                ("musicbrainz_recording_id", "MUSICBRAINZ_TRACKID"),
            ):
                if target.get(field) is not None:
                    audio[key] = str(target[field])
            audio["PIG_MUSIC_SOURCE"] = source
            audio.save()
            return
        if path.suffix == ".m4a":
            audio = MP4(path)
            if audio.tags is None:
                audio.add_tags()
            for key, field in (
                ("\xa9nam", "title"),
                ("\xa9ART", "artist"),
                ("\xa9alb", "album"),
                ("aART", "album_artist"),
            ):
                audio[key] = [target[field]]
            audio["trkn"] = [(target["track_number"], 0)]
            audio["disk"] = [(target["disc_number"], 0)]
            if target.get("year"):
                audio["\xa9day"] = [str(target["year"])]
            audio["----:com.apple.iTunes:PIG_MUSIC_SOURCE"] = [
                MP4FreeForm(source.encode())
            ]
            for field, description in (
                ("musicbrainz_release_id", "MusicBrainz Album Id"),
                ("musicbrainz_recording_id", "MusicBrainz Track Id"),
            ):
                if target.get(field):
                    audio["----:com.apple.iTunes:" + description] = [
                        MP4FreeForm(target[field].encode())
                    ]
            audio.save()
            return
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        for key, cls, value in [
            ("TIT2", TIT2, target["title"]),
            ("TPE1", TPE1, target["artist"]),
            ("TALB", TALB, target["album"]),
            ("TPE2", TPE2, target["album_artist"]),
            ("TRCK", TRCK, str(target["track_number"])),
            ("TPOS", TPOS, str(target["disc_number"])),
        ]:
            tags.delall(key)
            tags.add(cls(encoding=3, text=value))
        if target.get("year"):
            tags.delall("TDRC")
            tags.add(TDRC(encoding=3, text=str(target["year"])))
        tags.add(TXXX(encoding=3, desc="PIG_MUSIC_SOURCE", text=source))
        for field, description in (
            ("musicbrainz_release_id", "MusicBrainz Album Id"),
            ("musicbrainz_recording_id", "MusicBrainz Track Id"),
        ):
            if target.get(field):
                tags.delall("TXXX:" + description)
                tags.add(TXXX(encoding=3, desc=description, text=target[field]))
        tags.save(path, v2_version=3)

    def complete(self, job, path, extension, source, profile):
        self.check(job["id"])
        self.state(job["id"], "validating", effective_quality=profile)
        probe = self.validate(path, job, profile)
        if (
            job.get("exact_quality")
            and profile == "mp3_128"
            and probe["bitrate_kbps"] > 144
        ):
            raise ValueError("Replacement must be a genuine MP3 128 kbps source")
        self.tag(path, job, source)
        self.check(job["id"])
        filename = f"{job['disc_number']:02}-{job['track_number']:02} {safe_name(job['title'])} [{job['id'][:8]}]{extension}"
        target = (
            self.library_root
            / safe_name(job["album_artist"])
            / safe_name(job["album"])
            / filename
        )
        self.store.publish_request(
            job, path, target, probe, hashlib.sha256(path.read_bytes()).hexdigest()
        )

    def attempt(self, job, profile, errors):
        effective = {**job, "quality_profile": profile}
        for source in self.store.download_settings()["sources"]:
            self.check(job["id"])
            if source != "soulseek" and (
                profile == "lossless"
                or (profile == "aac_256") != (source == "jiosaavn")
            ):
                continue
            try:
                if source not in self.providers and source != "soulseek":
                    continue
                self.state(
                    job["id"], "searching", source=source, effective_quality=profile
                )
                candidates = (
                    self.soulseek.search(effective, lambda: self.check(job["id"]))
                    if source == "soulseek"
                    else (
                        self.paced_search(job, f"{job['artist']} {job['title']}")
                        if source == "freemp3cloud"
                        else self.providers[source](
                            f"{job['artist']} {job['title']}", 20
                        )
                    )
                )
                candidates = [c for c in candidates if matches(job, c)]
                if job.get("exact_quality") and profile == "mp3_128":
                    candidates = [
                        c
                        for c in candidates
                        if not re.search(
                            r"(?<!\d)(?:192|256|320)(?!\d)", str(c.get("quality", ""))
                        )
                    ]
                candidates.sort(key=lambda c: c.get("quality") != "320kbps")
                for candidate in candidates[:3]:
                    self.check(job["id"])
                    extension = (
                        candidate["extension"]
                        if source == "soulseek"
                        else ".m4a" if source == "jiosaavn" else ".mp3"
                    )
                    path = (
                        self.staging
                        / f"{job['id']}-{job.get('claim_token','legacy')}{extension}"
                    )
                    try:
                        self.state(
                            job["id"],
                            "downloading",
                            source=source,
                            effective_quality=profile,
                        )
                        self.transfer(job["id"], {**candidate, "source": source}, path)
                        self.complete(job, path, extension, source, profile)
                        return True
                    except (Cancelled, QualityDeadline):
                        raise
                    except Exception as exc:
                        message = (
                            "transfer failed"
                            if isinstance(exc, httpx.HTTPError)
                            else str(exc)[:160]
                        )
                        errors.append(f"{source}: {message}")
                    finally:
                        path.unlink(missing_ok=True)
                if not candidates:
                    errors.append(
                        f"{source}: no candidate passed recording/version matching"
                    )
            except (Cancelled, QualityDeadline):
                raise
            except Exception:
                errors.append(f"{source}: search unavailable")
        return False

    def process(self, job):
        self.context.claim_token = job.get("claim_token")
        errors = []
        desired = job.get(
            "quality_policy",
            policy(self.store.download_settings(), job.get("quality_profile")),
        )
        if desired["preferred"] == "mp3_128":
            job = {**job, "exact_quality": True}
        try:
            preferred = desired["preferred"]
            self.deadlines[job["id"]] = (
                time.monotonic() + desired["fallback_minutes"] * 60
            )
            try:
                if self.attempt(job, preferred, errors):
                    return
            except QualityDeadline:
                errors.append("Preferred quality attempt reached its time limit")
            finally:
                self.deadlines.pop(job["id"], None)
            fallback = desired["fallback"]
            if (
                preferred == "lossless"
                and fallback != "none"
                and not job.get("upgrade_only")
            ):
                if self.attempt(job, fallback, errors):
                    return
            # Last resort: AAC from JioSaavn, only when the owner enabled it as
            # a source, and only for requests made since this fallback existed.
            if (
                job.get("quality_policy", {}).get("aac_fallback")
                and "jiosaavn" in self.store.download_settings()["sources"]
                and not job.get("upgrade_only")
                and preferred != "aac_256"
                and not (preferred == "lossless" and fallback == "none")
            ):
                if self.attempt(job, "aac_256", errors):
                    return
            self.state(
                job["id"],
                "failed",
                error="; ".join(errors)[-1000:]
                or "No enabled source supports this request's quality profile",
            )
        except Cancelled:
            pass
        except Exception:
            self.state(
                job["id"],
                "failed",
                error="Acquisition interrupted; existing music retained. Retry this request.",
            )
        finally:
            self.deadlines.pop(job["id"], None)
