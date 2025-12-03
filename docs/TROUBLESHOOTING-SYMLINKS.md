# Troubleshooting Audiobookshelf Symlinks

## Current Status

✅ **Symlinks are correctly created** with host paths:
```
/mnt/user/upload/Other/Library/BLOOM-Library/Mitch Albom/The Time Keeper/The Time Keeper-Part01.mp3
  → /mnt/user/upload/Other/Library/Downloads/The Time Keeper/The Time Keeper-Part01.mp3
```

✅ **Symlinks are readable** from the Unraid host

## Why Audiobookshelf Can't See Files

### Docker Path Mapping Issue

If Audiobookshelf is running in Docker, it needs to have BOTH directories mounted:

1. **Source files** (where originals live):
   - Host: `/mnt/user/upload/Other/Library/Downloads`
   - Container: `/downloads` (or any path)

2. **Library files** (where organized symlinks are):
   - Host: `/mnt/user/upload/Other/Library/BLOOM-Library`
   - Container: `/audiobooks` (or whatever your library folder is named)

### The Problem

When Audiobookshelf scans `/audiobooks/Mitch Albom/The Time Keeper/`, it finds symlinks that point to:
```
/mnt/user/upload/Other/Library/Downloads/The Time Keeper/...
```

But from INSIDE the Audiobookshelf container, that path doesn't exist unless you also mount the Downloads folder!

## Solution Options

### Option 1: Mount Both Directories in Audiobookshelf (RECOMMENDED)

Update your Audiobookshelf docker-compose or run command to include both mounts:

```yaml
volumes:
  - /mnt/user/upload/Other/Library/BLOOM-Library:/audiobooks
  - /mnt/user/upload/Other/Library/Downloads:/downloads:ro  # Read-only is fine
  - /config:/config
  - /metadata:/metadata
```

Or with docker run:
```bash
docker run -d \
  --name=audiobookshelf \
  -v /mnt/user/upload/Other/Library/BLOOM-Library:/audiobooks \
  -v /mnt/user/upload/Other/Library/Downloads:/downloads:ro \
  -v /config:/config \
  -v /metadata:/metadata \
  -p 13378:80 \
  ghcr.io/advplyr/audiobookshelf:latest
```

### Option 2: Use Relative Symlinks (More Complex)

Modify the organizer to create relative symlinks instead of absolute ones. This would require significant code changes.

## Verify Audiobookshelf Configuration

1. **Check Library Settings** in Audiobookshelf:
   - Go to Settings → Libraries
   - Verify library folder path is `/audiobooks` (or whatever you mounted `/mnt/user/upload/Other/Library/BLOOM-Library` to)

2. **Run a Full Scan**:
   - Library → Click the 3 dots → "Re-Scan Library Items"
   - NOT just "Match All"

3. **Check Audiobookshelf Logs**:
   ```bash
   docker logs audiobookshelf --tail 100
   ```
   Look for permission errors or path not found errors

## Testing

After adding the Downloads mount to Audiobookshelf, test:

```bash
# From inside the Audiobookshelf container
docker exec audiobookshelf ls -la /audiobooks/Mitch\ Albom/The\ Time\ Keeper/
docker exec audiobookshelf file /audiobooks/Mitch\ Albom/The\ Time\ Keeper/The\ Time\ Keeper-Part01.mp3
```

If the symlinks resolve correctly inside the container, Audiobookshelf will be able to read them.

## Why This Happened

1. Librarian-bot creates symlinks with **absolute host paths** (e.g., `/mnt/user/upload/Other/Library/Downloads/...`)
2. These paths are correct from the Unraid **host** perspective
3. But Audiobookshelf runs in a **container** with its own filesystem view
4. Without mounting `/mnt/user/upload/Other/Library/Downloads` into the container, that path doesn't exist
5. Therefore, the symlinks appear broken to Audiobookshelf

## Alternative: Use Hardlinks (Won't Work)

Hardlinks don't work across different filesystems (which caused the original errno 18 error). This is why we switched to symlinks in the first place.

## Questions to Answer

1. Is Audiobookshelf running in Docker or directly on Unraid?
2. What volume mounts does your Audiobookshelf container have?
3. What is the configured library path in Audiobookshelf settings?

Run this to check Audiobookshelf mounts:
```bash
docker inspect audiobookshelf | grep -A 20 "Mounts"
```
