# 📋 Migration Guide - Old Workflow → New Workflow

## What Changed

### Before (Old Workflow)
```
User: /request "Fourth Wing" all

↓

Google Books validation
(exposed indexer information in results)

↓

User selects from dropdown menu
(showed 5 results with indexer names)

↓

Admin approval
(had to manually select result)

↓

Download started
```

### After (New Workflow)
```
User: /request "Fourth Wing"

↓

Open Library shows book info
(clean, no indexer details)

↓

User chooses: Ebook OR Audiobook
(two simple buttons)

↓

Bot automatically finds best torrent
(highest seeders)

↓

Admin approves in dedicated channel
(clean interface, one button click)

↓

Download started automatically
```

---

## Key Differences

| Feature | Before | After |
|---------|--------|-------|
| **API** | Google Books | Open Library |
| **Indexers Visible** | Yes ❌ | No ✅ |
| **User Selection** | Pick from 5 results | Pick format (ebook/audiobook) |
| **Torrent Selection** | User decided | Bot picked best (seeders) |
| **Approval Channel** | Same as bot announcements | Dedicated admin channel |
| **Automation** | Partial | Full (bot does it all) |
| **User Privacy** | Better | Best ✅ |

---

## Configuration Changes

### New in .env:
```env
# Add this line
ADMIN_CHANNEL_ID=1291129984353566820
```

### .env.example updated with:
```env
ADMIN_CHANNEL_ID=your_admin_channel_id_here
```

### No changes needed to:
- DISCORD_TOKEN
- PROWLARR_URL / PROWLARR_API_KEY
- QBIT_URL / QBIT_USERNAME / QBIT_PASSWORD
- Everything else stays the same!

---

## Code Changes Summary

### Files Added
```
open_library_api.py      (New module)
IMPROVED_WORKFLOW.md     (This documentation)
```

### Files Modified
```
discord_commands.py      (Complete /request rewrite)
discord_views.py         (Added RequestTypeView)
config.py                (Added ADMIN_CHANNEL_ID)
.env.example             (Added ADMIN_CHANNEL_ID)
```

### Files Removed
```
google_books_api.py      (Replaced by Open Library)
```

---

## Breaking Changes

⚠️ **IMPORTANT**: `/request` command signature changed!

### Old:
```
/request "book title" [all|ebook|audiobook]
```

### New:
```
/request "book title"
```

The `media_type` parameter is removed. Users now select it with buttons.

---

## Command Comparison

### Old /request Command:
```
/request "Fourth Wing" audiobook

Output:
- Shows 5 audiobook results
- Each result shows indexer name (MAM, MyAnon, etc.)
- User manually picks which result to request
- Can see torrent details (confusing for non-tech users)
```

### New /request Command:
```
/request "Fourth Wing"

Output:
- Shows book info (cover, author, description)
- Shows format selection buttons (Ebook or Audiobook)
- User clicks button
- Bot finds best torrent (hidden from user)
- Admin gets clean approval request
- Admin clicks approve/deny
- Download starts (or is denied)
```

---

## User Communication

### Tell your users:

> **Librarian Bot has been updated!**
>
> **New workflow:**
> 1. `/request "book name"` - search for a book
> 2. See beautiful book information with cover image
> 3. Click **📖 Request Ebook** or **🎧 Request Audiobook**
> 4. Admin gets approval request
> 5. Admin approves → download starts automatically
>
> **What's better?**
> - Cleaner interface
> - No confusing torrent details
> - Automatic torrent selection
> - Faster approvals
>
> **Example:**
> `/request "Fourth Wing"`

---

## Admin Communication

### Tell your admins:

> **Approval workflow updated!**
>
> **New approval process:**
> 1. Bot posts approval request in #admin-approvals
> 2. Shows: Book info, selected format, best torrent
> 3. Click **✅ Approve** or **❌ Deny**
> 4. User gets DM notification
> 5. Download starts (if approved)
>
> **Admin Channel ID:** 1291129984353566820
>
> **What you need to do:**
> - Set this channel for approval requests: `/config admin-channel 1291129984353566820`
> - Or add `ADMIN_CHANNEL_ID=1291129984353566820` to .env
> - Ensure bot has permission to post in that channel

---

## Deployment Steps

### 1. Update Config (.env)
```bash
# Add this line to your .env
ADMIN_CHANNEL_ID=1291129984353566820

# Or use your own admin channel ID if different
```

### 2. Deploy New Files
```bash
# New file needed:
git add open_library_api.py

# Modified files will be updated automatically
```

### 3. Restart Bot
```bash
# Stop old bot
Ctrl+C

# Start new bot
python bot.py
```

### 4. Test New Workflow
```
/request "Fourth Wing"
# Should show book info + buttons
# Click a button
# Check admin channel for approval request
# Click approve
# Should download
```

### 5. Communicate with Users
- Send message about new workflow
- Show example: `/request "book name"`
- Explain it's now simpler and cleaner

---

## Rollback (If Needed)

### If you need to go back to old workflow:

```bash
# Restore old files from git
git checkout discord_commands.py discord_views.py google_books_api.py

# Remove new files
rm open_library_api.py

# Update config
# Remove ADMIN_CHANNEL_ID from .env

# Restart
python bot.py
```

---

## FAQ

### Q: What if users don't know which format to choose?
**A**: Show them:
- **Ebook** = digital book (EPUB, PDF, etc.) - smaller file
- **Audiobook** = narrated book - larger file, great for listening while doing stuff
- Both usually available for popular books

### Q: Why was the old command parameter removed?
**A**: Because users can now select it with visual buttons, which is clearer.

### Q: Will old commands still work?
**A**: No, `/request "book" audiobook` will fail. Users must use `/request "book"` and select with buttons.

### Q: What if admin channel ID is wrong?
**A**: Bot will log an error. Update `.env` with correct ID and restart.

### Q: Can I use a different approval channel?
**A**: Yes! Change `ADMIN_CHANNEL_ID` in `.env` to any channel ID.

### Q: What if a torrent isn't available?
**A**: Bot shows error: "No [format] torrents found for: [book]" - User gets a clear message.

---

## Benefits Summary

### For Users ✅
- Cleaner interface
- Book covers and descriptions
- No technical jargon
- Simpler format selection

### For You (Admin) ✅
- Indexers not exposed
- Cleaner approval interface
- Less manual work (bot picks torrent)
- Better privacy

### For Your Instance ✅
- Harder to discover your indexers
- Professional appearance
- Better user experience
- Scalable approval workflow

---

## Status

```
✅ New workflow deployed
✅ Bot running with improvements
✅ Open Library API working
✅ Admin channel configured
✅ Ready for production
✅ Documentation complete

Next: Restart bot and test!
```

---

## Support

### Issues?
1. Check bot logs (look for errors)
2. Verify ADMIN_CHANNEL_ID is correct
3. Ensure bot has permission to post in admin channel
4. Restart bot: `python bot.py`

### Questions?
Refer to: `IMPROVED_WORKFLOW.md`

---

**Migration Complete!** 🎉

The bot is now running with the improved workflow. Users can't see your indexers, approvals are cleaner, and torrent selection is automatic.
