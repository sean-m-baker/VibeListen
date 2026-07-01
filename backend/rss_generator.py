from email.utils import formatdate
from typing import List
import xml.etree.ElementTree as ET
from backend.config import BASE_URL
from backend.database import Bookmark

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("content", CONTENT_NS)


def _itunes(tag: str) -> str:
    return f"{{{ITUNES_NS}}}{tag}"


def _make_text(parent: ET.Element, tag: str, text: str) -> ET.Element:
    elem = ET.SubElement(parent, tag)
    elem.text = text
    return elem


def format_duration(seconds: float) -> str:
    """Formats float duration in seconds into HH:MM:SS or MM:SS representation."""
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def generate_podcast_rss(completed_bookmarks: List[Bookmark], bitrate: str = "64") -> str:
    """
    Constructs a valid iTunes-compliant Podcast RSS 2.0 XML string
    from a list of successfully synthesized bookmarks.
    """
    bitrate_int = int(bitrate) if bitrate.isdigit() else 64

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    _make_text(channel, "title", "VibeListen Feed")
    _make_text(channel, "link", BASE_URL)
    _make_text(channel, "language", "en-us")
    _make_text(channel, _itunes("author"), "VibeListen Utility")
    _make_text(channel, _itunes("summary"), "Your personalized read-it-later podcast feed, powered by local synthesis.")
    _make_text(channel, "description", "Convert articles and bookmarks from Raindrop and Instapaper to speech.")

    owner = ET.SubElement(channel, _itunes("owner"))
    _make_text(owner, _itunes("name"), "VibeListen User")
    _make_text(owner, _itunes("email"), "user@VibeListen.local")

    _make_text(channel, _itunes("explicit"), "no")
    ET.SubElement(channel, _itunes("category"), text="Technology")
    ET.SubElement(channel, _itunes("image"), href=f"{BASE_URL}/frontend/podcast_art.png")

    for item in completed_bookmarks:
        if not item.audio_filename:
            continue

        duration_sec = item.audio_duration or 0.0

        if item.audio_filename.endswith(".wav"):
            mp3_filename = item.audio_filename.replace(".wav", ".mp3")
            audio_url = f"{BASE_URL}/rss-audio/{mp3_filename}"
            mime_type = "audio/mpeg"
            filesize = int((bitrate_int * 1000 / 8) * duration_sec) if duration_sec > 0 else (item.audio_filesize or 0)
        else:
            audio_url = f"{BASE_URL}/audio/{item.audio_filename}"
            mime_type = "audio/mpeg"
            filesize = item.audio_filesize or 0

        timestamp = item.added_at.timestamp()
        pub_date = formatdate(timestamp, usegmt=True)

        short_summary = item.clean_text[:400] + "..." if item.clean_text and len(item.clean_text) > 400 else (item.clean_text or "")

        entry = ET.SubElement(channel, "item")
        _make_text(entry, "title", item.title)
        _make_text(entry, _itunes("author"), item.author or "Unknown Author")
        _make_text(entry, "description", short_summary)
        _make_text(entry, "pubDate", pub_date)

        ET.SubElement(entry, "enclosure", url=audio_url, type=mime_type, length=str(filesize))

        guid = item.raindrop_id or item.instapaper_id or item.id
        _make_text(entry, "guid", f"VibeListen_{guid}").set("isPermaLink", "false")

        _make_text(entry, _itunes("duration"), format_duration(duration_sec))
        _make_text(entry, _itunes("explicit"), "no")

    return ET.tostring(rss, encoding="unicode", xml_declaration=True)
