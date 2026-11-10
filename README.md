# Shorts Maker

Link (YouTube, Kick, Google Drive, direct) ya file se vertical 9:16 short banata hai,
text hook aur colorful word-by-word captions ke saath. Upload limit 2GB (config me badha sakte ho).

## Setup
1. Python 3.10+ aur **ffmpeg** install karo (Windows: `winget install ffmpeg`, Mac: `brew install ffmpeg`)
2. `pip install -r requirements.txt`
3. `streamlit run app.py`

## Notes
- 2GB+ files ke liye "Local path" tab use karo (RAM nahi khata).
- Drive link "Anyone with the link" public hona chahiye.
- Kick/YouTube na chale to: `pip install -U yt-dlp`
- Sirf apni ya permission wali videos use karo.
