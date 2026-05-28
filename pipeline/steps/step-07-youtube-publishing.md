# Step 07: YouTube Publishing

## Agent
Publish Pioneer 🚀

## Objective
Upload the final video to YouTube with full metadata and custom thumbnail.

## Inputs
- `script_path`: Path to `{output_dir}/script/script.json`
- `video_path`: Path to `{output_dir}/final/final_video.mp4`
- `thumbnail_path`: Path to `{output_dir}/thumbnail/thumbnail.png`
- `privacy`: "private" | "unlisted" | "public"

## Dependencies
- Step 05 (final video must exist)
- Step 06 (thumbnail must exist)
- **CHECKPOINT**: User must approve final video before publishing

## Process
1. Read script.json for metadata (title, description, tags)
2. Authenticate with YouTube API via OAuth2
3. Build video metadata body
4. Upload video using resumable upload protocol
5. Set custom thumbnail
6. Set privacy status (default: private)
7. Save result to `publish_result.json`
8. Report video URL and Studio link

## Expected Output
- `{output_dir}/publish_result.json`
- Video accessible at returned YouTube URL

## YouTube Configuration
- Category: "1" (Film & Animation) for all content types
- Privacy: defaults to "private"
- Made for Kids: always false

## First-Time Setup
On first run, the OAuth2 flow will open a browser for authorization.
After that, credentials are cached in `.youtube_credentials.json`.

## Command
```bash
python scripts/publish_youtube.py --script-path "{output_dir}/script/script.json" --video-path "{output_dir}/final/final_video.mp4" --thumbnail-path "{output_dir}/thumbnail/thumbnail.png" --privacy "private"
```
