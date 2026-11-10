import shutil, subprocess, uuid
from pathlib import Path
import streamlit as st

BASE = Path(__file__).parent
WORK, OUT = BASE / "work", BASE / "outputs"
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)


def bgr(hex_rgb):
    """'#RRGGBB' -> 'BBGGRR' (ASS format)"""
    h = hex_rgb.lstrip("#")
    return f"{h[4:6]}{h[2:4]}{h[0:2]}"


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-1500:])
    return p.stdout


def download(url, folder):
    if "drive.google.com" in url or "docs.google.com" in url:
        import gdown
        out = gdown.download(url=url, output=str(folder / "src.mp4"), fuzzy=True, quiet=True)
        if not out:
            raise RuntimeError("Drive link public nahi hai (Anyone with link) ya limit lagi hai.")
        return Path(out)
    import yt_dlp
    opts = {"outtmpl": str(folder / "src.%(ext)s"), "noplaylist": True, "quiet": True,
            "format": "bv*[height<=1080]+ba/b[height<=1080]/b", "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])
    files = [f for f in folder.glob("src.*") if f.suffix not in (".part", ".ytdl")]
    if not files:
        raise RuntimeError("Download nahi hua. Link check karo.")
    return files[0]


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", str(path)]).strip())


def ts(s):
    cs = round(s * 100)
    return f"{cs // 360000}:{cs % 360000 // 6000:02d}:{cs % 6000 // 100:02d}.{cs % 100:02d}"


LANGS = {"Auto detect": None, "Hindi": "hi", "Urdu": "ur", "English": "en"}


@st.cache_resource
def load_model(size):
    from faster_whisper import WhisperModel
    return WhisperModel(size, device="cpu", compute_type="int8")


def transcribe(audio, size, lang):
    """Speech to text with exact word timing."""
    segs, _ = load_model(size).transcribe(str(audio), word_timestamps=True,
                                          language=lang, vad_filter=True)
    words = []
    for sg in segs:
        for w in sg.words or []:
            txt = w.word.strip().replace("{", "").replace("}", "")
            if txt:
                words.append((w.start, w.end, txt))
    return words


def spread_words(text, total):
    """Paragraph ke words ko poori clip me barabar (word length ke hisaab se) failata hai."""
    words = [w.replace("{", "").replace("}", "") for w in text.split()]
    words = [w for w in words if w]
    if not words:
        return []
    weights = [len(w) + 2 for w in words]
    scale = total / sum(weights)
    out, t = [], 0.0
    for w, wt in zip(words, weights):
        out.append((t, t + wt * scale, w))
        t += wt * scale
    return out


def make_ass(words, hook, font, size, text_c, hl_c, per_group, upper, pos,
             hook_secs, word_hl, hook_bg, hook_fg):
    mv = 380 if pos == "Bottom" else 0
    al = 2 if pos == "Bottom" else 5
    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,{font},{size},&H00{text_c},&H00{text_c},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,7,0,{al},70,70,{mv},1
Style: Hook,{font},{int(size * 0.9)},&H00{hook_fg},&H00{hook_fg},&H00{hook_bg},&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,230,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    if hook:
        ass += f"Dialogue: 1,{ts(0)},{ts(hook_secs)},Hook,,0,0,0,,{hook.replace(chr(10), ' ')}\n"
    hl, base = f"&H{hl_c}&", f"&H{text_c}&"
    for g in range(0, len(words), per_group):
        grp = words[g:g + per_group]
        if not word_hl:  # poora group ek hi color me
            txt = " ".join(w.upper() if upper else w for _, _, w in grp)
            ass += f"Dialogue: 0,{ts(grp[0][0])},{ts(grp[-1][1])},Cap,,0,0,0,,{{\\1c{hl}}}{txt}\n"
            continue
        for i, (s, e, _) in enumerate(grp):
            end = grp[i + 1][0] if i + 1 < len(grp) else e
            parts = []
            for j, (_, _, w) in enumerate(grp):
                w = w.upper() if upper else w
                parts.append(f"{{\\1c{hl}}}{w}{{\\1c{base}}}" if j == i else w)
            ass += f"Dialogue: 0,{ts(s)},{ts(max(end, s + 0.05))},Cap,,0,0,0,,{' '.join(parts)}\n"
    return ass


# ---------------- UI ----------------
st.set_page_config(page_title="Shorts Maker", layout="centered")
st.title("🎬 Shorts Maker")
st.caption("Link ya file -> vertical short + apna hook + apne captions")

with st.sidebar:
    st.header("Settings")
    mode = st.radio("Video fit", ["Blur background", "Fill (crop)"])
    st.subheader("Auto captions")
    model_size = st.selectbox("Whisper model", ["tiny", "base", "small"], index=1,
                              help="tiny = tez, small = zyada sahi")
    lang = st.selectbox("Language", list(LANGS))
    st.subheader("Captions style")
    hl_c = st.color_picker("Highlight color", "#FFE600")
    text_c = st.color_picker("Normal text color", "#FFFFFF")
    word_hl = st.checkbox("Word-by-word highlight", True)
    per_group = st.slider("Words at a time", 1, 8, 3)
    fsize = st.slider("Font size", 60, 140, 95)
    upper = st.checkbox("UPPERCASE", True)
    pos = st.radio("Position", ["Bottom", "Center"])
    font = st.text_input("Font", "Arial")
    st.subheader("Hook style")
    hook_bg = st.color_picker("Hook box color", "#FFE600")
    hook_fg = st.color_picker("Hook text color", "#000000")
    hook_secs = st.slider("Hook seconds", 1, 8, 3)

t1, t2, t3 = st.tabs(["🔗 Link", "📁 Upload (2GB)", "💻 Local path"])
url = t1.text_input("Video link", placeholder="https://youtube.com/... / kick.com/... / drive.google.com/...")
up = t2.file_uploader("Video file", type=["mp4", "mkv", "mov", "webm", "avi"])
local = t3.text_input("Full file path", placeholder=r"C:\Videos\stream.mp4  (2GB+ ke liye best)")

c1, c2 = st.columns(2)
start = c1.number_input("Start (seconds)", min_value=0, value=0, step=1)
length = c2.number_input("Length (seconds)", min_value=5, max_value=180, value=45, step=1)

hook = st.text_input("Hook text", placeholder="Shuru me aane wala bada text (khali = nahi lagega)")
cap_mode = st.radio("Captions", ["Auto (bolne se)", "Manual (apna paragraph)", "Off"], horizontal=True)
caption_text = ""
if cap_mode.startswith("Manual"):
    caption_text = st.text_area("Captions paragraph", height=180,
                                placeholder="Yahan poora caption paragraph likho. Ye video ki length me barabar chalega.")

if st.button("🚀 Generate Short", type="primary", use_container_width=True):
    job = WORK / uuid.uuid4().hex[:8]
    job.mkdir()
    try:
        with st.status("Kaam chal raha hai...", expanded=True) as status:
            st.write("Video le raha hoon")
            if url.strip():
                src = download(url.strip(), job)
            elif up is not None:
                src = job / ("src" + Path(up.name).suffix)
                with open(src, "wb") as f:
                    shutil.copyfileobj(up, f, 16 * 1024 * 1024)
            elif local.strip() and Path(local.strip().strip('"')).exists():
                src = Path(local.strip().strip('"'))
            else:
                raise RuntimeError("Link, upload ya path me se kuch do.")
            src = src.resolve()

            total = duration(src)
            if start >= total:
                raise RuntimeError(f"Start video se bada hai (video {int(total)} sec ka hai).")
            dur = min(length, total - start)

            words = []
            if cap_mode.startswith("Auto"):
                st.write("Speech to text (pehli baar model download hoga)")
                wav = job / "a.wav"
                run(["ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(src),
                     "-vn", "-ac", "1", "-ar", "16000", str(wav)])
                words = transcribe(wav, model_size, LANGS[lang])
                if not words:
                    st.warning("Awaaz nahi mili, captions nahi lage.")
            elif cap_mode.startswith("Manual"):
                words = spread_words(caption_text, dur)
            ass = make_ass(words, hook.strip(), font, fsize, bgr(text_c), bgr(hl_c), per_group,
                           upper, pos, hook_secs, word_hl, bgr(hook_bg), bgr(hook_fg))
            (job / "subs.ass").write_text(ass, encoding="utf-8")

            st.write("Vertical video bana raha hoon")
            if mode == "Blur background":
                fc = ("[0:v]split=2[a][b];"
                      "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                      "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                      "[bg][fg]overlay=(W-w)/2:(H-h)/2,ass=subs.ass[v]")
            else:
                fc = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,ass=subs.ass[v]"
            out = (OUT / f"short_{job.name}.mp4").resolve()
            run(["ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(src),
                 "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)], cwd=job)
            status.update(label="Ho gaya ✅", state="complete")

        st.video(str(out))
        with open(out, "rb") as f:
            st.download_button("⬇️ Download Short", f, file_name=out.name, mime="video/mp4",
                               use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")
    finally:
        shutil.rmtree(job, ignore_errors=True)
