"""Concurrent, recoverable acquisition with guarded NAS publication.

Source parsers are reused from Music Grabber; transfer, validation, tagging
and publication are app-owned. Preview/test storage remains isolated by default.
"""

import asyncio
import hashlib
import math
import os
import re
import shutil
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
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from .soulseek import Soulseek

from .audio import probe_file, validate_streams
from .providers import REGISTRY, SEARCH_PROVIDERS, supports
from .providers.process import run_checked
from .providers.contracts import Context, ProviderError
from .providers.runtime import Runtime
from .providers.legacy import search as legacy_search
from .providers.network import transfer as http_transfer
from .quality import CODEC_EXTENSIONS, policy, satisfies
from .storage import download_root, file_sha256, library_root

PROVIDERS = SEARCH_PROVIDERS
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
        return (
            float(value) if not isinstance(value, bool) and math.isfinite(value) else 0
        )
    try:
        parts = [float(v) for v in str(value).split(":")]
        return sum(v * 60**i for i, v in enumerate(reversed(parts)))
    except ValueError:
        return 0


def matches(target, candidate):
    for key in ("musicbrainz_recording_id", "musicbrainz_release_id"):
        if target.get(key) and candidate.get(key) and target[key] != candidate[key]:
            return False

    def isrcs(value):
        raw = value.get("isrcs") or value.get("isrc") or []
        if isinstance(raw, str):
            raw = [raw]
        return {str(code).strip().upper() for code in raw if code}

    requested_isrcs, candidate_isrcs = isrcs(target), isrcs(candidate)
    if (
        requested_isrcs
        and candidate_isrcs
        and requested_isrcs.isdisjoint(candidate_isrcs)
    ):
        return False
    if (
        candidate.get("source") in {"youtube", "soundcloud", "monochrome"}
        and target.get("album")
        and candidate.get("album")
        and folded(target["album"]) != folded(candidate["album"])
    ):
        return False
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
    def __init__(self, store, providers=None, runtime=None):
        self.store = store
        self.providers = providers if providers is not None else PROVIDERS
        self.runtime = runtime or Runtime(store)
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
            self.soulseek.transfer(
                candidate,
                path,
                lambda: self.check(job_id),
                lambda received, total: self.store.progress(job_id, received, total),
            )
            return {}
        context = Context(
            candidate.get("effective_profile", "native_standard"),
            check=lambda: self.check(job_id),
            progress=lambda received, total: self.store.progress(
                job_id, received, total, getattr(self.context, "claim_token", None)
            ),
            deadline=min(
                self.deadlines.get(job_id, float("inf")),
                getattr(self.context, "source_deadline", float("inf")),
                time.monotonic() + 180,
            ),
        )
        if REGISTRY[source].adapter:
            return self.runtime.transfer(source, candidate, path, context)
        context.max_bytes = 80_000_000
        http_transfer(
            candidate["source_url"], REGISTRY[source].download_hosts, path, context
        )
        return {}

    def validate(self, path, target, profile, decode=True, check=lambda: None):
        probe = probe_file(path, check)
        expected_codec = (
            "flac"
            if profile == "lossless"
            else "aac" if profile == "aac_256" else "mp3"
        )
        if not probe or (
            profile != "native_standard" and probe["codec"] != expected_codec
        ):
            raise ValueError(
                f"Downloaded content is not readable {expected_codec.upper()} for this quality profile"
            )
        validate_streams(path, check)
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
        if not satisfies(profile, probe):
            raise ValueError(
                "Downloaded audio does not meet the selected quality profile"
            )
        if CODEC_EXTENSIONS.get(probe["codec"]) != path.suffix.lower():
            raise ValueError("Downloaded codec does not match its audio container")
        if probe["duration"] <= 0:
            raise ValueError("Downloaded recording has no readable duration")
        if target.get("duration") and abs(probe["duration"] - target["duration"]) > 5:
            raise ValueError("Downloaded recording has the wrong duration")
        if decode:
            self.decode(path, check)
        return probe

    def decode(self, path, check=lambda: None):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise ValueError("FFmpeg is required to validate the complete recording")
        result = run_checked(
            [
                ffmpeg,
                "-v",
                "error",
                "-xerror",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(path),
                "-f",
                "null",
                "-",
            ],
            check,
            timeout=90,
        )
        if result.returncode:
            raise ValueError("The downloaded audio failed complete decoding")

    def tag(self, path, target, source):
        if path.suffix in {".flac", ".opus", ".ogg"}:
            audio = {".flac": FLAC, ".opus": OggOpus, ".ogg": OggVorbis}[path.suffix](
                path
            )
            if audio.tags is None:
                audio.add_tags()
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

    def complete(self, job, path, extension, source, profile, provenance=None):
        self.check(job["id"])
        self.state(job["id"], "validating", effective_quality=profile)
        probe = self.validate(
            path, job, profile, decode=False, check=lambda: self.check(job["id"])
        )
        if (
            job.get("exact_quality")
            and profile == "mp3_128"
            and probe["bitrate_kbps"] > 144
        ):
            raise ValueError("Replacement must be a genuine MP3 128 kbps source")
        self.tag(path, job, source)
        self.decode(path, lambda: self.check(job["id"]))
        probe["acquisition"] = {
            "provider": source,
            "quality_profile": profile,
            "codec": probe["codec"],
            "container": probe["container"],
            "bitrate_kbps": probe["bitrate_kbps"],
            "duration": probe["duration"],
            "sample_rate_hz": probe["sample_rate_hz"],
            "channels": probe["channels"],
            "validated_at": int(time.time()),
            **(provenance or {}),
        }
        self.check(job["id"])
        filename = f"{job['disc_number']:02}-{job['track_number']:02} {safe_name(job['title'])} [{job['id'][:8]}]{extension}"
        target = (
            self.library_root
            / safe_name(job["album_artist"])
            / safe_name(job["album"])
            / filename
        )
        self.store.publish_request(job, path, target, probe, file_sha256(path))

    def attempt(self, job, profile, errors):
        effective = {**job, "quality_profile": profile}
        for source in self.store.download_settings()["sources"]:
            self.check(job["id"])
            if not supports(source, profile):
                continue
            self.context.source_deadline = min(
                self.deadlines.get(job["id"], float("inf")), time.monotonic() + 240
            )
            try:
                if (
                    source not in self.providers
                    and source != "soulseek"
                    and not REGISTRY[source].adapter
                ):
                    continue
                self.state(
                    job["id"], "searching", source=source, effective_quality=profile
                )
                context = Context(
                    profile,
                    check=lambda: self.check(job["id"]),
                    deadline=min(
                        self.context.source_deadline,
                        time.monotonic() + 90,
                    ),
                )
                if REGISTRY[source].adapter:
                    candidates = self.runtime.search(source, effective, context)
                else:
                    with self.runtime.health.operation(source):
                        if source == "soulseek":
                            candidates = self.soulseek.search(
                                effective, lambda: self.check(job["id"])
                            )
                        elif self.providers[source] is REGISTRY[source].search:
                            candidates = legacy_search(
                                source, f"{job['artist']} {job['title']}", context
                            )
                        else:
                            candidates = self.providers[source](
                                f"{job['artist']} {job['title']}", 20
                            )
                        self.runtime.health.outcome(source)
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
                    extension = REGISTRY[source].extension(candidate)
                    path = (
                        self.staging
                        / f"{job['id']}-{job.get('claim_token','legacy')}{extension}"
                    )
                    transferred = False
                    try:
                        self.state(
                            job["id"],
                            "downloading",
                            source=source,
                            effective_quality=profile,
                        )
                        provenance = self.transfer(
                            job["id"],
                            {
                                **candidate,
                                "source": source,
                                "effective_profile": profile,
                            },
                            path,
                        )
                        transferred = True
                        self.complete(job, path, extension, source, profile, provenance)
                        self.runtime.health.outcome(source, transfer=True)
                        return True
                    except (Cancelled, QualityDeadline):
                        raise
                    except Exception as exc:
                        if transferred:
                            self.runtime.health.outcome(
                                source, error=ProviderError("no_match"), transfer=True
                            )
                        elif not REGISTRY[source].adapter:
                            self.runtime.health.outcome(
                                source,
                                error=(
                                    exc
                                    if isinstance(exc, ProviderError)
                                    else ProviderError("no_match")
                                ),
                                transfer=True,
                            )
                        message = (
                            "transfer failed"
                            if isinstance(exc, httpx.HTTPError)
                            else (
                                str(exc)[:160]
                                if isinstance(exc, ValueError)
                                else "candidate validation failed"
                            )
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
            except ProviderError as exc:
                errors.append(f"{source}: {exc}")
            except Exception:
                self.runtime.health.outcome(source, error=ProviderError())
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
                self.deadlines[job["id"]] = (
                    time.monotonic() + desired["fallback_minutes"] * 60
                )
                try:
                    if self.attempt(job, fallback, errors):
                        return
                except QualityDeadline:
                    errors.append("Fallback quality attempt reached its time limit")
                finally:
                    self.deadlines.pop(job["id"], None)
            # Last resort: AAC from JioSaavn, only when the owner enabled it as
            # a source, and only for requests made since this fallback existed.
            if (
                job.get("quality_policy", {}).get("aac_fallback")
                and "jiosaavn" in self.store.download_settings()["sources"]
                and not job.get("upgrade_only")
                and preferred != "aac_256"
                and not (preferred == "lossless" and fallback == "none")
            ):
                self.deadlines[job["id"]] = (
                    time.monotonic() + desired["fallback_minutes"] * 60
                )
                try:
                    if self.attempt(job, "aac_256", errors):
                        return
                except QualityDeadline:
                    errors.append("AAC fallback attempt reached its time limit")
                finally:
                    self.deadlines.pop(job["id"], None)
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
