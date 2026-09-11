"""JPEG DateTimeOriginal parser — the LeadMarket gallery-date helper."""

import struct
import unittest

from crm.tests.frappe_shim import install

install()

from crm.api.photo_exif import _allowed, jpeg_datetime  # noqa: E402


def _jpeg_with_ascii(tag, text="2024:03:15 14:22:01"):
	"""Minimal JPEG + APP1 Exif, one IFD0 ASCII tag (big-endian TIFF)."""
	payload = text.encode("ascii") + b"\x00"
	# TIFF: MM 002a, IFD at 8, 1 entry, next-IFD 0, then the string.
	ifd_count = struct.pack(">H", 1)
	entry = struct.pack(">HHI", tag, 2, len(payload)) + struct.pack(">I", 26)
	next_ifd = struct.pack(">I", 0)
	tiff = b"MM\x00\x2a" + struct.pack(">I", 8) + ifd_count + entry + next_ifd + payload
	app1 = b"Exif\x00\x00" + tiff
	seglen = struct.pack(">H", 2 + len(app1))
	return b"\xff\xd8\xff\xe1" + seglen + app1 + b"\xff\xda\x00\x02"


class JpegDatetimeTests(unittest.TestCase):
	def test_datetimeoriginal(self):
		data = _jpeg_with_ascii(0x9003, "2024:03:15 14:22:01")
		self.assertEqual(jpeg_datetime(data), "2024-03-15T14:22:01")

	def test_datetime_file_clock_fallback(self):
		# 0x0132 is DateTime (file clock). Used when DateTimeOriginal is absent.
		data = _jpeg_with_ascii(0x0132, "2023:11:02 08:00:00")
		self.assertEqual(jpeg_datetime(data), "2023-11-02T08:00:00")

	def test_not_jpeg(self):
		self.assertEqual(jpeg_datetime(b"\x89PNG"), "")

	def test_empty(self):
		self.assertEqual(jpeg_datetime(b""), "")

	def test_malformed_segment_does_not_raise(self):
		self.assertEqual(jpeg_datetime(b"\xff\xd8\xff\xe1\x00\x02"), "")

	def test_allowed_gallery_cdn(self):
		self.assertTrue(_allowed("https://photos.zillowstatic.com/fp/abc.jpg"))
		self.assertTrue(_allowed("https://ap.rdcpix.com/x.jpg"))

	def test_rejects_streetview_and_ssrf(self):
		self.assertFalse(_allowed("https://maps.googleapis.com/maps/api/streetview?location=1,2"))
		self.assertFalse(_allowed("http://127.0.0.1/secret"))
		self.assertFalse(_allowed("https://evil.example/x.jpg"))
