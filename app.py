from __future__ import annotations

import re
from dotenv import load_dotenv
import os

import streamlit as st


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")


def _gemini_api_key() -> str | None:
    key = (api_key or "").strip()
    return key or None


def _gemini_model() -> str:
    return (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip() or "gemini-2.5-flash"


_HEADING_ORDER = ("Short Summary", "Detailed Summary", "Key Points")


def _extract_sections(raw_text: str) -> tuple[dict[str, str], bool]:
    """Extract Short/Detailed/Key sections from model output.

    Handles variations like:
      - ## Short Summary
      - 1. Short Summary
      - Short Summary:

    Returns (sections, ok). If ok=False, UI should fall back to showing raw.
    """

    text = (raw_text or "").strip()
    if not text:
        return ({"Short Summary": "", "Detailed Summary": "", "Key Points": ""}, False)

    header_pattern = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\d+\.\s*)?(Short Summary|Detailed Summary|Key Points)\s*[:\-]?\s*$",
        re.I | re.M,
    )
    matches = list(header_pattern.finditer(text))
    if not matches:
        return ({"Short Summary": "", "Detailed Summary": "", "Key Points": ""}, False)

    sections: dict[str, str] = {"Short Summary": "", "Detailed Summary": "", "Key Points": ""}
    for index, match in enumerate(matches):
        title = match.group(1).strip().title()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if title in sections:
            sections[title] = text[start:end].strip()

    ok = all((sections[name] or "").strip() for name in ("Short Summary", "Detailed Summary", "Key Points"))
    return (sections, ok)


def _coerce_bullets(text: str) -> str:
    content = (text or "").strip()
    if not content:
        return ""

    lines = [line.rstrip() for line in content.splitlines() if line.strip()]
    if any(line.lstrip().startswith(("- ", "* ")) for line in lines):
        normalized: list[str] = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                normalized.append(f"- {stripped[2:].strip()}")
            elif stripped.startswith("* "):
                normalized.append(f"- {stripped[2:].strip()}")
            else:
                normalized.append(f"- {stripped.strip()}")
        return "\n".join(normalized)

    single_line = re.sub(r"\s+", " ", content).strip()
    return f"- {single_line}"


def _normalize_block(text: str) -> str:
    block = (text or "").strip()
    if not block:
        return ""
    return block


def _ensure_formatted_markdown(raw: str) -> str:
    """Ensure output has required headings and bullets.

    Returns Markdown with:
      ## Short Summary
      ## Detailed Summary
      ## Key Points
    and bullet points under each heading.
    """

    text = (raw or "").strip()
    if not text:
        return (
            "## Short Summary\n\n"
            "## Detailed Summary\n\n"
            "## Key Points\n"
        )

    pattern_md = re.compile(r"^\s*#{1,6}\s*(Short Summary|Detailed Summary|Key Points)\s*$", re.I | re.M)
    pattern_num = re.compile(r"^\s*\d+\.\s*(Short Summary|Detailed Summary|Key Points)\s*[:\-]?\s*$", re.I | re.M)
    pattern_colon = re.compile(r"^\s*(Short Summary|Detailed Summary|Key Points)\s*:\s*$", re.I | re.M)
    matches = (
        list(pattern_md.finditer(text))
        or list(pattern_num.finditer(text))
        or list(pattern_colon.finditer(text))
    )

    sections: dict[str, str] = {}
    if matches:
        for index, match in enumerate(matches):
            title = match.group(1).strip().title()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections[title] = text[start:end].strip()

    if not all(name in sections for name in _HEADING_ORDER):
        # Heuristic fallback: use first ~4 sentences for short, full text for detailed.
        compact = re.sub(r"\s+", " ", text).strip()
        sentences = re.split(r"(?<=[.!?])\s+", compact)
        short = " ".join([s for s in sentences if s][:4]).strip()
        sections = {
            "Short Summary": short or compact,
            "Detailed Summary": compact,
            "Key Points": "",
        }

    short_md = _normalize_block(sections.get("Short Summary", ""))
    detailed_md = _normalize_block(sections.get("Detailed Summary", ""))
    key_points_md = _coerce_bullets(sections.get("Key Points", ""))

    return (
        "## Short Summary\n"
        f"{short_md}\n\n"
        "## Detailed Summary\n"
        f"{detailed_md}\n\n"
        "## Key Points\n"
        f"{key_points_md}"
    )


def _format_fallback(text: str) -> str:
    trimmed = (text or "").strip()
    if not trimmed:
        trimmed = "(empty input)"

    short = trimmed[:240]
    detailed = trimmed[:900]
    bullets = [
        "This is a fallback response because GEMINI_API_KEY is not set.",
        "Set GEMINI_API_KEY in .env to enable real summaries.",
        "Then click 'Generate Summary'.",
    ]

    return (
        "## Short Summary\n"
        f"{short}{'...' if len(trimmed) > len(short) else ''}\n\n"
        "## Detailed Summary\n"
        f"{detailed}{'...' if len(trimmed) > len(detailed) else ''}\n\n"
        "## Key Points\n"
        + "\n".join(f"- {b}" for b in bullets)
    )


def summarize(text: str) -> str:
    """Summarize user text using the Google Gemini API.

    Requires GEMINI_API_KEY in the environment. Returns Markdown with headings:
    - Short Summary (3-4 lines)
    - Detailed Summary
    - Key Points
    """

    api_key = _gemini_api_key()
    if not api_key:
        return _format_fallback(text)

    prompt = f"""
You are a professional summarization assistant.

Analyze the given text and return ONLY the following sections:

Short Summary:
- 3–4 concise lines

Detailed Summary:
- Clear paragraph explaining the content

Key Points:
- Bullet points only
- No extra text before or after sections

Do NOT include explanations like "Here is a summary".
Keep output clean and structured.

Text:
{text}
""".strip()

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=_gemini_model(), contents=prompt)
        output_text = (getattr(response, "text", None) or "").strip()
        if not output_text:
            return _format_fallback(text)
        return output_text
    except Exception:
        return _format_fallback(text)


def _decode_uploaded_txt(raw: bytes) -> str:
    if not raw:
        return ""

    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _render_summary_block(text: str) -> None:
    content = (text or "").strip()
    if not content:
        st.markdown("No summary extracted")
        return

    # Bold each non-empty line for readability.
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) <= 1:
        st.markdown(f"**{lines[0] if lines else content}**")
        return

    for line in lines:
        st.markdown(f"**{line}**")


def run_streamlit_app() -> None:
    st.set_page_config(page_title="AI Document Summarizer", layout="centered")
    st.title("AI Document Summarizer")
    st.caption("Summarize text or a .txt file using Gemini 2.5 Flash.")

    if "last_raw" not in st.session_state:
        st.session_state["last_raw"] = ""

    with st.expander("Input", expanded=True):
        st.text_area(
            "Text input",
            key="input_text",
            height=220,
            placeholder="Paste a long document here...",
        )
        st.file_uploader(
            "Upload a .txt file",
            key="uploaded_file",
            type=["txt"],
            accept_multiple_files=False,
        )

    left, right = st.columns(2)
    with left:
        generate = st.button("Generate Summary", type="primary", use_container_width=True)
    with right:
        clear = st.button("Clear Input", use_container_width=True)

    if clear:
        st.session_state["input_text"] = ""
        st.session_state["uploaded_file"] = None
        st.session_state["last_raw"] = ""
        st.rerun()

    if generate:
        uploaded = st.session_state.get("uploaded_file")
        input_text = st.session_state.get("input_text", "")

        if uploaded is not None:
            text = _decode_uploaded_txt(uploaded.getvalue())
        else:
            text = input_text

        if not (text or "").strip():
            st.warning("Please provide text or upload a .txt file.")
            return

        with st.spinner("Generating summary..."):
            result = summarize(text)

        st.session_state["last_raw"] = result
        st.success("Summary generated successfully!")

    raw = (st.session_state.get("last_raw") or "").strip()
    if not raw:
        return

    extracted, ok = _extract_sections(raw)
    if not ok:
        st.markdown(raw)
        return

    short_summary = _normalize_block(extracted.get("Short Summary", ""))
    detailed_summary = _normalize_block(extracted.get("Detailed Summary", ""))
    key_points = _coerce_bullets(extracted.get("Key Points", ""))

    st.subheader("📝 Short Summary")
    _render_summary_block(short_summary)

    st.write("")
    st.divider()
    st.write("")

    st.subheader("📖 Detailed Summary")
    _render_summary_block(detailed_summary)

    st.write("")
    st.divider()
    st.write("")

    st.subheader("🔑 Key Points")
    st.markdown(key_points or "No key points extracted")


run_streamlit_app()
