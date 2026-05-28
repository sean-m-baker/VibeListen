from email.utils import formatdate
from typing import List
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape
from backend.config import BASE_URL
from backend.database import Bookmark

def format_duration(seconds: float) -> str:
    """Formats float duration in seconds into HH:MM:SS or MM:SS representation."""
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    secs = s % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def generate_podcast_rss(completed_bookmarks: List[Bookmark]) -> str:
    """
    Constructs a valid iTunes-compliant Podcast RSS 2.0 XML string
    from a list of successfully synthesized bookmarks.
    """
    base_url_escaped = escape(BASE_URL)
    
    # Core RSS Header
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" ',
        '     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" ',
        '     xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        '  <channel>',
        f'    <title>{escape("VibeListen Feed")}</title>',
        f'    <link>{base_url_escaped}</link>',
        '    <language>en-us</language>',
        f'    <itunes:author>{escape("VibeListen Utility")}</itunes:author>',
        f'    <itunes:summary>{escape("Your personalized read-it-later podcast feed, powered by local synthesis.")}</itunes:summary>',
        f'    <description>{escape("Convert articles and bookmarks from Raindrop and Instapaper to speech.")}</description>',
        '    <itunes:owner>',
        f'      <itunes:name>{escape("VibeListen User")}</itunes:name>',
        f'      <itunes:email>{escape("user@VibeListen.local")}</itunes:email>',
        '    </itunes:owner>',
        '    <itunes:explicit>no</itunes:explicit>',
        '    <itunes:category text="Technology"/>',
        f'    <itunes:image href="{base_url_escaped}/frontend/podcast_art.png" />'
    ]

    for item in completed_bookmarks:
        if not item.audio_filename:
            continue

        # Format absolute audio source link
        audio_url = f"{BASE_URL}/audio/{item.audio_filename}"
        audio_url_escaped = escape(audio_url)
        
        # Build pubDate in RFC 822 standard format
        timestamp = item.added_at.timestamp()
        pub_date = formatdate(timestamp, usegmt=True)
        
        # Estimate/Fetch sizing info
        filesize = item.audio_filesize or 0
        duration_sec = item.audio_duration or 0.0
        duration_str = format_duration(duration_sec)

        # Truncate summary if too long for standard XML RSS descriptions
        short_summary = item.clean_text[:400] + "..." if item.clean_text and len(item.clean_text) > 400 else (item.clean_text or "")
        
        xml.append('    <item>')
        xml.append(f'      <title>{escape(item.title)}</title>')
        xml.append(f'      <itunes:author>{escape(item.author or "Unknown Author")}</itunes:author>')
        xml.append(f'      <description>{escape(short_summary)}</description>')
        xml.append(f'      <pubDate>{pub_date}</pubDate>')
        xml.append(f'      <enclosure url="{audio_url_escaped}" type="audio/mpeg" length="{filesize}" />')
        xml.append(f'      <guid isPermaLink="false">VibeListen_{item.raindrop_id}</guid>')
        xml.append(f'      <itunes:duration>{duration_str}</itunes:duration>')
        xml.append('      <itunes:explicit>no</itunes:explicit>')
        xml.append('    </item>')

    xml.append('  </channel>')
    xml.append('</rss>')

    return "\n".join(xml)
