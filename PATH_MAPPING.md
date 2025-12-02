# Cross-Server Path Mapping Guide

## Problem

When running Librarian Bot on a distributed setup:
- **qBittorrent** runs on **Seedbox** (e.g., `/mnt/downloads`)
- **library_organizer.py** runs on **Unraid** (e.g., `/mnt/user/library`)
- Paths reported by qBit don't exist locally on Unraid

## Solution: Path Mapping

The `path_mapper.py` module translates paths between servers so `library_organizer.py` can work with files on the correct server.

---

## Setup Steps

### 1. Enable Path Mapping in `.env`

```env
# Enable path mapping
ENABLE_PATH_MAPPING=true

# Which server runs the bot/organizer
SERVER_MODE=remote  # or "local" if on same server, "seedbox" if on seedbox

# Seedbox Configuration (where qBit downloads)
SEEDBOX_HOST=192.168.1.50
SEEDBOX_USER=admin
SEEDBOX_PASSWORD=seedbox_password
SEEDBOX_SSH_PORT=22
SEEDBOX_DOWNLOAD_PATH=/mnt/downloads

# Unraid Configuration (where bot runs)
UNRAID_HOST=192.168.1.100
UNRAID_USER=root
UNRAID_PASSWORD=unraid_password
UNRAID_LIBRARY_PATH=/mnt/user/library

# Map seedbox paths to unraid paths
# Format: SEEDBOX_PATH|UNRAID_PATH;SEEDBOX_PATH2|UNRAID_PATH2
PATH_MAPPINGS=/mnt/downloads|/mnt/user/downloads;/mnt/media|/mnt/user/media
```

### 2. Server Mode Options

#### `SERVER_MODE=local`
- Bot and qBit on same server
- No path mapping needed
- Use local paths directly

#### `SERVER_MODE=remote`
- Bot runs on Unraid
- qBit runs on Seedbox
- Paths translated from seedbox → unraid
- library_organizer runs on Unraid
- SSH access to Seedbox for file operations

#### `SERVER_MODE=seedbox`
- Bot runs on Seedbox
- library_organizer runs on Seedbox
- No path mapping needed
- Access to qBit local files directly

### 3. Path Mapping Rules

Define mappings for each path on seedbox that has a different path on unraid:

```env
PATH_MAPPINGS=/mnt/downloads|/mnt/user/downloads;/mnt/media|/mnt/user/media
```

**Example translations:**
- Seedbox: `/mnt/downloads/book.epub` → Unraid: `/mnt/user/downloads/book.epub`
- Seedbox: `/mnt/media/audio.m4b` → Unraid: `/mnt/user/media/audio.m4b`

---

## How It Works

### Flow with Path Mapping

```
1. User approves download on Unraid (bot)
   ↓
2. qBittorrent on Seedbox downloads to: /mnt/downloads/file.epub
   ↓
3. Bot monitors completion via qBit API
   ↓
4. qBit reports path: /mnt/downloads/file.epub
   ↓
5. Path Mapper translates:
   /mnt/downloads/file.epub → /mnt/user/downloads/file.epub
   ↓
6. library_organizer receives mapped path on Unraid
   ↓
7. Checks if file is accessible (local or via SSH)
   ↓
8. Organizes and creates hardlinks in: /mnt/user/library/Author/Title/
```

### Without Path Mapping (Would fail)

```
qBit reports: /mnt/downloads/file.epub
Unraid tries to access: /mnt/downloads/file.epub
❌ ERROR: Path doesn't exist on Unraid!
```

---

## API Usage

### In Code

```python
from path_mapper import get_path_mapper, map_torrent_path

# Get mapper instance
mapper = get_path_mapper()

# Map a path
torrent_path = "/mnt/downloads/book.epub"  # From qBit
local_path = mapper.get_local_path(torrent_path)
# Returns: /mnt/user/downloads/book.epub

# Check if file exists on seedbox
if mapper.file_exists_on_seedbox(torrent_path):
    print("File exists on seedbox")

# Copy file from seedbox to unraid
mapper.copy_from_seedbox(torrent_path, "/mnt/user/books/file.epub")

# Or use convenience function
local_path = map_torrent_path("/mnt/downloads/book.epub")
```

### Integration with library_organizer

```python
# In library_organizer.py
from path_mapper import map_torrent_path

def organize_download(torrent_path):
    # Map seedbox path to local unraid path
    local_path = map_torrent_path(torrent_path)
    
    # Now use local_path with library operations
    # Create hardlinks, organize files, etc.
    ...
```

---

## Example Configurations

### Configuration 1: Same Server (Simplest)

```env
ENABLE_PATH_MAPPING=false
SERVER_MODE=local
QBIT_DOWNLOAD_PATH=/mnt/downloads
LIBRARY_PATH=/mnt/library
```

**Result:** No path translation, direct file access

---

### Configuration 2: Seedbox + Unraid (Most Common)

```env
ENABLE_PATH_MAPPING=true
SERVER_MODE=remote

# Seedbox
SEEDBOX_HOST=seedbox.example.com
SEEDBOX_USER=seedbox_user
SEEDBOX_PASSWORD=seedbox_pass
SEEDBOX_SSH_PORT=22
SEEDBOX_DOWNLOAD_PATH=/mnt/downloads

# Unraid (where bot runs)
UNRAID_HOST=192.168.1.100
UNRAID_USER=root
UNRAID_PASSWORD=unraid_pass
UNRAID_LIBRARY_PATH=/mnt/user/library

# Map paths
PATH_MAPPINGS=/mnt/downloads|/mnt/user/downloads
```

**Result:**
- Bot runs on Unraid
- qBit runs on Seedbox
- Files copied via SFTP when needed
- Paths automatically translated

---

### Configuration 3: Complex Multi-Mount Setup

```env
ENABLE_PATH_MAPPING=true
SERVER_MODE=remote

SEEDBOX_HOST=seedbox.example.com
SEEDBOX_USER=admin
SEEDBOX_PASSWORD=password
SEEDBOX_SSH_PORT=22
SEEDBOX_DOWNLOAD_PATH=/mnt/downloads

UNRAID_HOST=192.168.1.100
UNRAID_USER=root
UNRAID_PASSWORD=password
UNRAID_LIBRARY_PATH=/mnt/user/library

# Multiple mount points
PATH_MAPPINGS=/mnt/downloads|/mnt/user/downloads;/mnt/media|/mnt/user/media;/mnt/library|/mnt/user/library
```

**Result:**
- Multiple paths automatically translated
- Each seedbox path maps to unraid equivalent

---

## SSH Requirements

For `SERVER_MODE=remote`, you need SSH access to seedbox:

### Seedbox SSH Setup

```bash
# 1. Enable SSH on seedbox
# (Usually already enabled on most seedbox providers)

# 2. Get seedbox IP/hostname and credentials
SEEDBOX_HOST=your.seedbox.com
SEEDBOX_USER=your_username
SEEDBOX_PASSWORD=your_password

# 3. Test SSH connection
ssh -p 22 your_username@your.seedbox.com
# Should connect without errors
```

### Alternative: SSH Key Authentication

For security, consider using SSH keys instead of passwords:

```env
# Still use password in .env for backward compatibility
# But SSH key auth can be added in future version
```

---

## Troubleshooting

### Issue: "Path doesn't exist on seedbox"

```
ERROR: /mnt/downloads/book.epub not found on seedbox
```

**Solution:**
- Verify `SEEDBOX_DOWNLOAD_PATH` is correct
- Check path mapping rules in `PATH_MAPPINGS`
- Ensure SSH credentials are valid

### Issue: "Cannot connect to seedbox"

```
ERROR: Failed to connect to seedbox: Connection refused
```

**Solution:**
- Verify `SEEDBOX_HOST` is correct IP/hostname
- Check `SEEDBOX_SSH_PORT` (usually 22)
- Verify SSH password is correct
- Check firewall allows SSH from Unraid to Seedbox

### Issue: "Path mapping not working"

```
# After mapping, path is still wrong
```

**Solution:**
- Verify `ENABLE_PATH_MAPPING=true`
- Check `PATH_MAPPINGS` format: `SOURCE|DEST`
- Verify paths start with correct seedbox path
- Check logs for path translation details

---

## Performance Considerations

### Hardlinks vs Copies

- **Hardlinks (preferred):** No extra disk space, instant operation
- **Copies:** Full file copy, uses extra space, slower

With path mapping:
- If file already accessible on unraid mount → hardlink
- If file only on seedbox → copy via SFTP (slower)

### Optimization Tips

1. **Mount seedbox storage on Unraid** (via NFS/SMB)
   - No SSH needed
   - Instant hardlink creation
   - Better performance

2. **Or set `ENABLE_HARDLINKS=false`**
   - Creates copies instead of links
   - No need for same mount point
   - But uses extra disk space

3. **Cache frequently used paths**
   - Mapper caches translations
   - Subsequent calls are instant

---

## Testing Path Mapper

```python
# Test script
from config import Config
from path_mapper import get_path_mapper

# Enable for testing
Config.ENABLE_PATH_MAPPING = True
Config.PATH_MAPPINGS = {
    "/mnt/downloads": "/mnt/user/downloads"
}

mapper = get_path_mapper()

# Test mapping
result = mapper.map_path("/mnt/downloads/book.epub", "seedbox_to_unraid")
print(result)  # Should output: /mnt/user/downloads/book.epub

# Test reverse mapping
result = mapper.map_path("/mnt/user/downloads/book.epub", "unraid_to_seedbox")
print(result)  # Should output: /mnt/downloads/book.epub
```

---

## Summary

| Feature | Value |
|---------|-------|
| Automatic path translation | ✅ Yes |
| SSH support | ✅ Yes |
| SFTP file transfer | ✅ Yes |
| Multiple mount points | ✅ Yes |
| Fallback to no mapping | ✅ Yes |
| Caching | ✅ Yes |

**Next:** Integrate path mapper into bot.py and library_organizer.py to use these mappings when processing torrents.
