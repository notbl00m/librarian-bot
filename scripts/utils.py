"""
Utility functions for Librarian Bot
Shared helpers used across modules
"""

import os
import re
from typing import Optional, List, Tuple
from pathlib import Path
from datetime import datetime


def format_size(bytes_size: int) -> str:
    """
    Format bytes to human-readable size (B, KB, MB, GB, TB)
    
    Args:
        bytes_size: Size in bytes
        
    Returns:
        Human-readable size string
    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def format_duration(seconds: int) -> str:
    """
    Format seconds to human-readable duration (s, m, h, d)
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Human-readable duration string
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def format_percentage(value: float, total: float) -> str:
    """
    Format a percentage
    
    Args:
        value: Current value
        total: Total value
        
    Returns:
        Formatted percentage string
    """
    if total == 0:
        return "0%"
    percentage = (value / total) * 100
    return f"{percentage:.1f}%"


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to be filesystem-safe
    
    Args:
        filename: Filename to sanitize
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "", filename)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(". ")
    
    # Replace multiple spaces with single space
    sanitized = re.sub(r"\s+", " ", sanitized)
    
    return sanitized


def extract_author_from_text(text: str) -> Optional[str]:
    """
    Try to extract author name from text
    Common patterns: "Author Name -", "by Author Name", "Author Name:"
    
    Args:
        text: Text to search
        
    Returns:
        Author name if found, None otherwise
    """
    patterns = [
        r"by\s+([A-Z][a-zA-Z\s\.]+?)(?:\s*-|\s*\(|$)",  # by Author Name
        r"([A-Z][a-zA-Z\s\.]+?)\s*(?:-|by|:)",  # Author Name -/by/:
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            author = match.group(1).strip()
            # Filter out common noise
            if len(author) > 2 and len(author) < 100:
                return author
    
    return None


def validate_url(url: str) -> bool:
    """
    Validate if a string is a valid URL
    
    Args:
        url: URL string to validate
        
    Returns:
        True if valid URL, False otherwise
    """
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(url_pattern.match(url))


def ensure_dir_exists(path: str) -> Path:
    """
    Ensure a directory exists, creating it if necessary
    
    Args:
        path: Directory path
        
    Returns:
        Path object
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_file_extension(filename: str) -> str:
    """
    Get file extension (including the dot)
    
    Args:
        filename: Filename
        
    Returns:
        Extension with dot, e.g., ".epub"
    """
    return Path(filename).suffix.lower()


def is_audio_format(filename: str) -> bool:
    """
    Check if file is an audio format
    
    Args:
        filename: Filename to check
        
    Returns:
        True if audio format
    """
    from config import Config

    ext = get_file_extension(filename)
    return ext in Config.SUPPORTED_AUDIO_FORMATS


def is_ebook_format(filename: str) -> bool:
    """
    Check if file is an ebook format
    
    Args:
        filename: Filename to check
        
    Returns:
        True if ebook format
    """
    from config import Config

    ext = get_file_extension(filename)
    return ext in Config.SUPPORTED_EBOOK_FORMATS


def is_supported_format(filename: str) -> bool:
    """
    Check if file is a supported audio or ebook format
    
    Args:
        filename: Filename to check
        
    Returns:
        True if supported format
    """
    return is_audio_format(filename) or is_ebook_format(filename)


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to max length
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def parse_magnet_link(magnet: str) -> Optional[dict]:
    """
    Parse magnet link and extract info
    
    Args:
        magnet: Magnet link string
        
    Returns:
        Dict with xt (hash), dn (display name), tr (trackers), or None if invalid
    """
    if not magnet.startswith("magnet:?"):
        return None

    params = {}
    for param in magnet.replace("magnet:?", "").split("&"):
        if "=" in param:
            key, value = param.split("=", 1)
            params[key] = value

    if "xt" not in params:
        return None

    return params


def get_timestamp() -> str:
    """
    Get current timestamp in ISO format
    
    Returns:
        ISO formatted timestamp
    """
    return datetime.now().isoformat()


def clean_discord_markdown(text: str) -> str:
    """
    Clean text for Discord to avoid formatting issues
    
    Args:
        text: Text to clean
        
    Returns:
        Cleaned text
    """
    # Escape Discord markdown characters
    text = text.replace("`", "\\`")
    text = text.replace("*", "\\*")
    text = text.replace("_", "\\_")
    text = text.replace("~", "\\~")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    return text


def format_discord_code_block(text: str, language: str = "") -> str:
    """
    Format text as Discord code block
    
    Args:
        text: Text to format
        language: Programming language for syntax highlighting
        
    Returns:
        Formatted code block
    """
    return f"```{language}\n{text}\n```"


def split_into_chunks(text: str, max_length: int = 2000) -> List[str]:
    """
    Split text into chunks for Discord messages (max 2000 chars per message)
    
    Args:
        text: Text to split
        max_length: Maximum length per chunk
        
    Returns:
        List of text chunks
    """
    chunks = []
    current_chunk = ""

    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += ("\n" if current_chunk else "") + line

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def create_progress_bar(
    current: int, total: int, width: int = 10, filled: str = "█", empty: str = "░"
) -> str:
    """
    Create a progress bar
    
    Args:
        current: Current progress
        total: Total amount
        width: Width of progress bar
        filled: Character for filled portion
        empty: Character for empty portion
        
    Returns:
        Progress bar string
    """
    if total == 0:
        percentage = 0
    else:
        percentage = (current / total) * 100

    filled_width = int((percentage / 100) * width)
    empty_width = width - filled_width

    bar = filled * filled_width + empty * empty_width
    return f"[{bar}] {percentage:.1f}%"


def is_valid_discord_mention(mention: str) -> bool:
    """
    Check if string is a valid Discord user mention
    
    Args:
        mention: String to check (should be <@USER_ID>)
        
    Returns:
        True if valid mention
    """
    return bool(re.match(r"^<@!?\d+>$", mention))


def extract_user_id_from_mention(mention: str) -> Optional[int]:
    """
    Extract user ID from Discord mention
    
    Args:
        mention: Discord mention string
        
    Returns:
        User ID or None if invalid
    """
    match = re.match(r"^<@!?(\d+)>$", mention)
    if match:
        return int(match.group(1))
    return None


def calculate_eta(current: int, total: int, elapsed_seconds: int) -> Optional[str]:
    """
    Calculate estimated time to completion
    
    Args:
        current: Current progress
        total: Total amount
        elapsed_seconds: Elapsed time in seconds
        
    Returns:
        Formatted ETA or None if unable to calculate
    """
    if current == 0 or current >= total:
        return None

    remaining = total - current
    rate = current / elapsed_seconds
    eta_seconds = remaining / rate

    return format_duration(int(eta_seconds))


def normalize_path(path: str) -> str:
    """
    Normalize file path to use forward slashes
    
    Args:
        path: File path
        
    Returns:
        Normalized path
    """
    return Path(path).as_posix()


def get_safe_filename(title: str, author: str = "", extension: str = "") -> str:
    """
    Generate a safe filename from title and author
    
    Args:
        title: Book title
        author: Author name (optional)
        extension: File extension (optional)
        
    Returns:
        Safe filename
    """
    if author:
        filename = f"{author} - {title}"
    else:
        filename = title

    filename = sanitize_filename(filename)
    
    if extension:
        if not extension.startswith("."):
            extension = "." + extension
        filename += extension

    return filename
