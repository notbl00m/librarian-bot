# Librarian Bot - Complete Workflow

## End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DISCORD USER                                │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
                      /request "The Name of the Wind"
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ discord_commands.py: request_command()                              │
│ ├─ Receives query from Discord user                                 │
│ ├─ Calls: search_prowlarr(query, category, limit=5)                │
│ └─ Displays top 5 results with dropdown selector                    │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ prowlarr_api.py: search()                                            │
│ ├─ Makes async HTTP request to Prowlarr                             │
│ ├─ Searches ALL configured indexers (MyAnonamouse, etc.)            │
│ ├─ Returns: List[SearchResult] with:                                │
│ │  • title                                                           │
│ │  • download_url (magnet link or .torrent)                         │
│ │  • seeders/leechers                                               │
│ │  • size                                                            │
│ │  • indexer name                                                    │
│ │  • publish_date                                                    │
│ └─ Calculates health_score (seeders/leechers ratio)                │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ discord_commands.py: Display Results                                │
│ ├─ Creates embeds for each result (top 5)                           │
│ ├─ Shows: Title, Indexer, Size, Seeders, Published Date            │
│ ├─ Adds SearchResultsView dropdown with all results                 │
│ ├─ Pagination for browsing (if >1 result)                           │
│ └─ Waits for user selection (timeout: 5 minutes)                    │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
                   User selects result (clicks dropdown)
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ discord_views.py: SearchResultSelect.callback()                     │
│ ├─ User clicks dropdown and selects result #2                       │
│ ├─ Stores selection in pending_requests dict                        │
│ ├─ Tells user: "Selected: [Title] - Awaiting admin approval"        │
│ └─ Triggers approval request to admins                              │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ discord_commands.py: _send_approval_request()                       │
│ ├─ Creates approval embed with:                                     │
│ │  • Requester name                                                  │
│ │  • Title, Indexer, Size, Seeders                                  │
│ ├─ Adds AdminApprovalView (✅/❌ buttons)                             │
│ ├─ Sends to admin channel (or current channel if none)              │
│ └─ Timeout: 10 minutes                                              │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
                        ADMIN DECISION POINT
                                 ↓
                    ┌─────────────────────────────┐
                    │                             │
              ✅ APPROVE                    ❌ DENY
                    │                             │
                    ↓                             ↓
         ┌──────────────────────┐    ┌──────────────────────┐
         │ _approve_download()  │    │ _deny_download()     │
         └──────────────────────┘    └──────────────────────┘
                    ↓                             ↓
            Adds to qBittorrent         Notify user: Denied
            Notifies requester              No download
                                            
                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│ discord_commands.py: _approve_download()                            │
│ ├─ Sends approval embed to admin channel                            │
│ ├─ Connects to qBittorrent client                                   │
│ ├─ Calls: client.add_torrent(download_url)                          │
│ │  • download_url can be magnet link or .torrent URL               │
│ │  • Sets category: "librarian-bot"                                 │
│ │  • Sets save path: Config.QBIT_DOWNLOAD_PATH                     │
│ ├─ Gets torrent hash for tracking                                   │
│ ├─ Sends DM to requester: "Download approved! Added to queue"       │
│ └─ Logs: Requester + Approver + Torrent hash                        │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ qBit Downloads                                                       │
│ ├─ qBittorrent starts downloading torrent                           │
│ ├─ Files go to: QBIT_DOWNLOAD_PATH                                  │
│ ├─ Category: "librarian-bot"                                        │
│ ├─ Seeders help: bot.py monitor_torrents() checks completion        │
│ └─ User can track via: /status command                              │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ bot.py: monitor_torrents() - Background Task                        │
│ ├─ Runs every 5 seconds (configurable)                              │
│ ├─ Polls qBittorrent for category "librarian-bot"                   │
│ ├─ Checks: torrent.progress >= 1.0 (100% complete)                 │
│ ├─ On completion:                                                    │
│ │  • Marks hash as processed (avoid duplicate processing)           │
│ │  • Logs: "🎉 Torrent completed: [Name]"                           │
│ │  • [TODO] Triggers library_organizer.py                           │
│ │  • [TODO] Notifies user via DM                                    │
│ └─ Continues monitoring other active torrents                       │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
            ⚠️  INTEGRATION POINT (To Be Implemented)
                   library_organizer.py
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ library_organizer.py: organize_download()                           │
│ ├─ INPUT: Torrent hash + Downloaded file path                       │
│ ├─ STEP 1: Extract Files                                            │
│ │  • Find .cbr, .cbz, .epub, .mp3, .m4b etc in download folder     │
│ │  • Identify format (audiobook vs ebook)                           │
│ ├─ STEP 2: Get Metadata (Google Books API)                          │
│ │  • Search by filename                                              │
│ │  • Extract: Author Name, Title, Series                            │
│ │  • Example: "Patrick Rothfuss, The Name of the Wind, 1"           │
│ ├─ STEP 3: Create Directory Structure                               │
│ │  • LIBRARY_PATH/Author Name/Book Title/                           │
│ │  • Example: /library/Patrick Rothfuss/The Name of the Wind/       │
│ ├─ STEP 4: Create Hardlinks (NOT copies)                            │
│ │  • Original file: QBIT_DOWNLOAD_PATH/[downloaded_file]            │
│ │  • Hardlink to: LIBRARY_PATH/Author/Book/[file]                   │
│ │  • Benefit: File counts for seeding but appears in library        │
│ │  • File takes no extra disk space                                  │
│ ├─ STEP 5: Track Processing                                         │
│ │  • Store in processed_items.json:                                 │
│ │    {                                                               │
│ │      "torrent_hash": "abc123",                                     │
│ │      "filename": "Name_of_the_Wind.epub",                          │
│ │      "author": "Patrick Rothfuss",                                 │
│ │      "title": "The Name of the Wind",                              │
│ │      "library_path": "/library/Patrick Rothfuss/...",              │
│ │      "processed_date": "2025-12-01T10:30:00"                       │
│ │    }                                                               │
│ └─ Avoid re-processing same file                                    │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Disk State After Organization                                       │
│                                                                      │
│ QBIT_DOWNLOAD_PATH (Original - Still Seeding):                      │
│ ├─ The_Name_of_the_Wind.epub                                        │
│ │  ↑ Physical file (being seeded)                                   │
│                                                                      │
│ LIBRARY_PATH (Organized):                                            │
│ ├─ Patrick Rothfuss/                                                │
│ │  ├─ The Name of the Wind/                                         │
│ │  │  └─ The_Name_of_the_Wind.epub                                  │
│ │  │     ↑ HARDLINK (points to same inode as original)              │
│ │  │     ✅ Counts for seeding                                       │
│ │  │     ✅ No extra disk space                                      │
│ │  ├─ The Wise Man's Fear/                                          │
│ │  │  └─ The_Wise_Mans_Fear.epub                                    │
│ │  │     ↑ HARDLINK                                                  │
│ │                                                                     │
│ └─ Stephen King/                                                     │
│    ├─ The Shining/                                                   │
│    │  └─ The_Shining.epub                                            │
│    │     ↑ HARDLINK                                                  │
└─────────────────────────────────────────────────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────┐
│ bot.py: Send Completion Notification                                │
│ ├─ Sends DM to original requester:                                  │
│ │  "✅ Download Complete & Organized!                               │
│ │   📚 Title: The Name of the Wind                                   │
│ │   ✍️  Author: Patrick Rothfuss                                     │
│ │   📂 Location: /library/Patrick Rothfuss/The Name of the Wind/     │
│ │   🌱 Still seeding for the community!"                             │
│ ├─ Posts summary to admin channel                                    │
│ └─ Marks task as complete                                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Step Breakdown

### 1️⃣ **SEARCH PHASE** (Prowlarr)
**User runs:** `/request "The Name of the Wind"`

**What happens:**
```python
# discord_commands.py
results = await search_prowlarr(
    query="The Name of the Wind",
    category=SearchCategory.ALL,
    limit=5
)

# prowlarr_api.py makes HTTP GET to:
# http://localhost:9696/api/v1/search?query=The Name of the Wind&type=search&limit=5
# Headers: X-Api-Key: [API_KEY]

# Returns 5 SearchResult objects:
[
  SearchResult(
    title="The Name of the Wind - Patrick Rothfuss [2007]",
    download_url="magnet:?xt=urn:btih:abc123...",
    seeders=150,
    leechers=25,
    size=450000000,  # 450 MB
    indexer="MyAnonamouse",
    publish_date="2025-11-20",
    guid="xyz789"
  ),
  # ... 4 more results ...
]
```

**User sees:**
- Embed with Result #1: Title, Indexer, Size (450 MB), Seeders (150), Published
- Dropdown selector to choose result
- Shows all 5 results via pagination buttons

---

### 2️⃣ **SELECTION PHASE** (Discord Views)
**User selects:** Result #1 from dropdown

**What happens:**
```python
# discord_views.py: SearchResultSelect
# User clicks "The Name of the Wind - Patrick Rothfuss [2007]"
# Discord calls: SearchResultSelect.callback()

# Stores in pending_requests:
pending_requests[user_id] = {
    "query": "The Name of the Wind",
    "results": [...],
    "selected_idx": 0,
    "selected_result": {
        "title": "The Name of the Wind - Patrick Rothfuss [2007]",
        "download_url": "magnet:?xt=urn:btih:abc123...",
        "seeders": 150,
        "indexer": "MyAnonamouse",
        "size": 450000000
    }
}

# Tells user: "✅ Selected: The Name of the Wind - Patrick Rothfuss [2007]
#              Awaiting admin approval..."
```

---

### 3️⃣ **APPROVAL PHASE** (Admin)
**Admin sees:** Approval request in admin channel

**What happens:**
```python
# discord_commands.py: _send_approval_request()

# Creates embed:
Embed(
    title="📥 Download Approval Requested",
    description="""
    Requester: @user#1234
    Title: The Name of the Wind - Patrick Rothfuss [2007]
    Indexer: MyAnonamouse
    Size: 450 MB
    Seeders: 150
    """
)

# Adds AdminApprovalView with:
# ✅ APPROVE button
# ❌ DENY button
# (with role check for ADMIN_ROLE)
```

**Admin clicks:** ✅ APPROVE

```python
# AdminApprovalView.handle_approve()
# ├─ Posts embed: "✅ Download Approved by @admin#5678"
# ├─ Calls: client.add_torrent(
#      "magnet:?xt=urn:btih:abc123...",
#      category="librarian-bot",
#      save_path="C:/Downloads"
#   )
# ├─ Gets back torrent hash: "hash_abc123"
# ├─ Sends DM to user: "✅ Download Approved!
#                       Title: The Name of the Wind
#                       Status: Added to download queue
#                       I'll notify you when complete and organized."
# └─ Logs: "Download approved for: The Name of the Wind (user_id, admin_id, hash)"
```

---

### 4️⃣ **DOWNLOAD PHASE** (qBittorrent)
**What happens:**
```python
# qbit_client.py: add_torrent()
# ├─ qBittorrent starts downloading
# ├─ Saves to: C:/Downloads
# ├─ Category: "librarian-bot"
# ├─ Speed: ~5-10 MB/s (depends on seeders)
# ├─ File: The_Name_of_the_Wind.epub (~450 MB)
# └─ Time to complete: ~45 seconds to 10 minutes

# Meanwhile, bot.py monitor_torrents() runs every 5 seconds:
while True:
    torrents = client.get_torrents_in_category("librarian-bot")
    for torrent in torrents:
        if torrent.progress >= 1.0:  # 100% complete
            # Trigger organization (NEXT PHASE)
    await asyncio.sleep(5)
```

**User can check:** `/status`
```
Shows:
📥 The Name of the Wind - Patrick Rothfuss [2007]
Progress: 87%
Size: 450 MB
Downloaded: 391.5 MB
Speed: ⬇️ 7.8 MB/s
State: downloading
```

---

### 5️⃣ **COMPLETION DETECTION** (Background Monitor)
**When torrent hits 100%:**

```python
# bot.py: monitor_torrents()
logger.info("🎉 Torrent completed: The Name of the Wind")

completed_hashes.add("hash_abc123")  # Mark as processed

# [TODO] Trigger library_organizer
# For now, just logs completion
```

---

### 6️⃣ **ORGANIZATION PHASE** (library_organizer.py)
**[INTEGRATION POINT - To be fully implemented]**

**Current state:** File in QBIT_DOWNLOAD_PATH
```
C:/Downloads/
└─ The_Name_of_the_Wind.epub  (450 MB - actively seeding)
```

**Steps library_organizer.py will perform:**

**STEP 1: Find Files**
```python
# In C:/Downloads, find all supported formats:
# .epub, .mobi, .pdf, .azw3 (ebooks)
# .m4b, .mp3, .m4a (audiobooks)
# .cbr, .cbz (comics)

files_to_organize = [
    "The_Name_of_the_Wind.epub"
]
```

**STEP 2: Get Metadata**
```python
# Use Google Books API search
# Query: "The Name of the Wind"
# Response:
{
    "items": [{
        "volumeInfo": {
            "title": "The Name of the Wind",
            "authors": ["Patrick Rothfuss"],
            "publishedDate": "2007-08-27",
            "description": "...",
            "imageLinks": {...}
        }
    }]
}

# Extract:
author = "Patrick Rothfuss"
title = "The Name of the Wind"
series = "The Kingkiller Chronicle"
series_index = 1
```

**STEP 3: Create Directory Structure**
```
LIBRARY_PATH = "C:/Library"

Target path: C:/Library/Patrick Rothfuss/The Name of the Wind/

Create if not exists:
├─ C:/Library/
├─ C:/Library/Patrick Rothfuss/
├─ C:/Library/Patrick Rothfuss/The Name of the Wind/
```

**STEP 4: Create Hardlinks**
```python
# Original (stays in place for seeding):
# C:/Downloads/The_Name_of_the_Wind.epub

# Create hardlink:
os.link(
    "C:/Downloads/The_Name_of_the_Wind.epub",
    "C:/Library/Patrick Rothfuss/The Name of the Wind/The_Name_of_the_Wind.epub"
)

# Result:
# • Both paths point to SAME FILE on disk
# • Same inode = same physical data
# • Counts for seeding stats
# • No extra disk space used
# • Deleting one unlinks, doesn't delete file until all links gone

# Disk usage: Still only 450 MB (not 900 MB)
```

**STEP 5: Track Processing**
```python
# Save to processed_items.json:
{
    "processed_items": [
        {
            "torrent_hash": "hash_abc123",
            "filename": "The_Name_of_the_Wind.epub",
            "author": "Patrick Rothfuss",
            "title": "The Name of the Wind",
            "series": "The Kingkiller Chronicle",
            "series_index": 1,
            "original_path": "C:/Downloads/The_Name_of_the_Wind.epub",
            "library_path": "C:/Library/Patrick Rothfuss/The Name of the Wind/The_Name_of_the_Wind.epub",
            "size_bytes": 450000000,
            "processed_date": "2025-12-01T10:35:00Z",
            "format": "epub"
        }
    ]
}
```

---

### 7️⃣ **NOTIFICATION PHASE** (User)
**After organization completes:**

```python
# bot.py: Send completion DM
await user.send(f"""
✅ **Download Complete & Organized!**

📚 **Title:** The Name of the Wind
✍️  **Author:** Patrick Rothfuss
📖 **Series:** The Kingkiller Chronicle (Book 1)
📂 **Location:** C:/Library/Patrick Rothfuss/The Name of the Wind/
💾 **Size:** 450 MB
🌱 **Status:** Still seeding for the community!

Enjoy your book! 📖
""")
```

---

## File State at Each Phase

### After Download (Before Organization)
```
C:/Downloads (QBIT_DOWNLOAD_PATH)
└─ The_Name_of_the_Wind.epub  (450 MB - SEEDING)

C:/Library (LIBRARY_PATH)
└─ (empty - not yet organized)
```

### After Organization (Hardlinks)
```
C:/Downloads (QBIT_DOWNLOAD_PATH)
└─ The_Name_of_the_Wind.epub  (450 MB - SEEDING)
   ↑ Physical file (inode 12345)

C:/Library (LIBRARY_PATH)
├─ Patrick Rothfuss/
│  ├─ The Name of the Wind/
│  │  └─ The_Name_of_the_Wind.epub  (HARDLINK → inode 12345)
│  │     ↑ Points to same file, no extra space
│  ├─ The Wise Man's Fear/
│  │  └─ The_Wise_Mans_Fear.epub
│  └─ ...other books...
├─ Stephen King/
│  ├─ The Shining/
│  └─ ...
└─ ...other authors...

Disk Used: Still 450 MB (not 900 MB)
Seeders Happy: File still counts for ratio tracking
Library Complete: Files organized and accessible
```

---

## Summary

| Phase | Duration | File Location | Status |
|-------|----------|---------------|---------| 
| Search | <1s | Prowlarr | Results in Discord |
| Selection | 5 min | pending_requests | Awaiting approval |
| Approval | 10 min | Discord | Admin decision |
| Download | 45s - 10m | QBIT_DOWNLOAD_PATH | Active torrent |
| Organization | ~5s | Both paths | Hardlinked |
| Complete | Instant | Both paths | User notified |

---

**Next: We need to implement the integration in bot.py to call library_organizer.py when torrents complete!**
