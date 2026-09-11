"""JPEG DateTimeOriginal for comps-gallery photos.

LeadMarket's auction ingest downloads each JPEG once, reads EXIF, and discards
the bytes. Same here, on the gallery request, with a short budget so the photos
themselves are never waiting on dates. Per-URL Redis cache, 30 days — a miss
(no EXIF) is remembered too, or a stripped CDN would be re-fetched forever.
"""
from __future__ import annotations

import hashlib
import re
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import urlparse

DOWNLOAD_TIMEOUT = 8
DOWNLOAD_MAX = 2_000_000
EXIF_CAP = 24
EXIF_BUDGET = 1.0
EXIF_WORKERS = 4
CACHE_SECONDS = 30 * 24 * 60 * 60
CACHE_PREFIX = "crm:photo-exif:v1:"

# Provider-synthesized Street View has no camera clock. Auction.com's imgix
# CDN strips EXIF (measured in LeadMarket).
_SKIP_HOSTS = (
	"maps.googleapis.com",
	"maps.gstatic.com",
	"adc-tenbox-prod.imgix.net",
)


def jpeg_datetime(data: bytes) -> str:
	"""DateTimeOriginal from a JPEG APP1 Exif segment, else ''."""
	if not data.startswith(b"\xff\xd8"):
		return ""
	i, n = 2, len(data)
	while i + 4 < n and data[i] == 0xFF:
		marker = data[i + 1]
		if marker == 0xDA:
			break
		seglen = int.from_bytes(data[i + 2 : i + 4], "big")
		if seglen < 2 or i + 2 + seglen > n:
			break
		payload = data[i + 4 : i + 2 + seglen]
		if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
			found = _tiff_datetime(payload[6:])
			if found:
				return found
		i += 2 + seglen
	return ""


def _tiff_datetime(tiff: bytes) -> str:
	if len(tiff) < 8:
		return ""
	endian = "<" if tiff[:2] == b"II" else ">" if tiff[:2] == b"MM" else ""
	if not endian:
		return ""
	try:
		off = struct.unpack(endian + "I", tiff[4:8])[0]
		return _ifd_datetime(tiff, off, endian) or ""
	except struct.error:
		return ""


def _ifd_datetime(tiff: bytes, off: int, endian: str) -> str:
	if off + 2 > len(tiff):
		return ""
	n = struct.unpack(endian + "H", tiff[off : off + 2])[0]
	pos = off + 2
	exif_off = None
	dates = {}
	for _ in range(n):
		if pos + 12 > len(tiff):
			break
		tag, typ, count = struct.unpack(endian + "HHI", tiff[pos : pos + 8])
		val = tiff[pos + 8 : pos + 12]
		pos += 12
		if tag == 0x8769:  # Exif IFD pointer
			exif_off = struct.unpack(endian + "I", val)[0]
		elif tag in (0x9003, 0x0132, 0x9004) and typ == 2:
			dates[tag] = _ascii_at(tiff, val, count, endian)
	if 0x9003 in dates:  # DateTimeOriginal
		return _exif_to_iso(dates[0x9003])
	if exif_off:
		nested = _ifd_datetime(tiff, exif_off, endian)
		if nested:
			return nested
	if 0x9004 in dates:
		return _exif_to_iso(dates[0x9004])
	if 0x0132 in dates:
		return _exif_to_iso(dates[0x0132])
	return ""


def _ascii_at(tiff: bytes, val: bytes, count: int, endian: str) -> str:
	if count <= 4:
		raw = val[:count]
	else:
		off = struct.unpack(endian + "I", val)[0]
		raw = tiff[off : off + count]
	return raw.split(b"\x00", 1)[0].decode("ascii", "ignore").strip()


def _exif_to_iso(s: str) -> str:
	m = re.match(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", s or "")
	if not m:
		return ""
	y, mo, d, h, mi, se = m.groups()
	return f"{y}-{mo}-{d}T{h}:{mi}:{se}"


def download_exif(url: str) -> str:
	"""Pure HTTP — safe on a worker thread (`frappe.local` is thread-local)."""
	try:
		req = urllib.request.Request(
			url,
			headers={
				"User-Agent": "Mozilla/5.0",
				"Accept": "image/jpeg,image/*;q=0.8",
			},
		)
		with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
			buf = b""
			while len(buf) < DOWNLOAD_MAX:
				chunk = resp.read(16_384)
				if not chunk:
					break
				buf += chunk
				if b"\xff\xda" in buf:  # SOS — EXIF lives before the scan
					break
		return jpeg_datetime(buf)
	except Exception:
		return ""


_ALLOW_SUFFIXES = (
	"zillowstatic.com",
	"zillow.com",
	"rdcpix.com",
	"redfin.com",
	"redfinstatic.com",
	"googleapis.com",
	"gstatic.com",
	"imgix.net",
)


def _skip(url: str) -> bool:
	if not url or not url.startswith("http"):
		return True
	host = (urlparse(url).netloc or "").split(":")[0].lower()
	return any(host == h or host.endswith("." + h) for h in _SKIP_HOSTS)


def _allowed(url: str) -> bool:
	"""Gallery CDNs only — this URL is fetched server-side."""
	if _skip(url):
		return False
	try:
		host = (urlparse(url).hostname or "").lower()
	except Exception:
		return False
	if not host or host in ("localhost",) or host.endswith(".local"):
		return False
	return any(host == s or host.endswith("." + s) for s in _ALLOW_SUFFIXES)


def _cache_key(url: str) -> str:
	return CACHE_PREFIX + hashlib.sha1(url.encode("utf-8")).hexdigest()


def stamp_urls(urls, budget=None, cap=None):
	"""Aligned ISO datetimes (or '') for `urls`. Never raises."""
	import frappe

	photos = [u if isinstance(u, str) else "" for u in (urls or [])]
	out = [""] * len(photos)
	budget = EXIF_BUDGET if budget is None else float(budget)
	cap = EXIF_CAP if cap is None else int(cap)
	cache = frappe.cache()
	need = []
	for i, url in enumerate(photos):
		if i >= cap or _skip(url):
			continue
		try:
			cached = cache.get_value(_cache_key(url))
		except Exception:
			cached = None
		if cached is not None:
			out[i] = cached or ""
		else:
			need.append(i)
	if not need:
		return out

	found = {}

	def _one(i):
		found[i] = download_exif(photos[i]) or ""

	# Hero first so the date on screen is the one that lands inside the budget.
	ordered = [need[0]] + need[1:]
	# shutdown(wait=False): a `with ThreadPoolExecutor` would block the gallery
	# on the remaining JPEG downloads after the budget.
	pool = ThreadPoolExecutor(max_workers=EXIF_WORKERS)
	try:
		futs = [pool.submit(_one, i) for i in ordered]
		wait(futs, timeout=max(0.05, budget))
	except Exception:
		pass
	finally:
		pool.shutdown(wait=False)
	for i in need:
		if i not in found:
			continue
		out[i] = found[i]
		try:
			cache.set_value(_cache_key(photos[i]), found[i], expires_in_sec=CACHE_SECONDS)
		except Exception:
			pass
	return out


def date_for_url(url: str) -> str:
	"""One JPEG, on its own request. Empty if the host is skipped or not a gallery CDN."""
	url = str(url or "").strip()
	if not _allowed(url):
		return ""
	out = stamp_urls([url], budget=float(DOWNLOAD_TIMEOUT), cap=1)
	return out[0] if out else ""
