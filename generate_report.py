#!/usr/bin/env python3
"""Generate a daily HTML news report using Gemini with Google Search grounding."""

import html as html_mod
import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3
OUTPUT_DIR = Path("output")
CENTRAL_TZ = ZoneInfo("America/Chicago")


def get_date_str():
    return datetime.now(CENTRAL_TZ).strftime("%A, %B %d, %Y")


def extract_grounding_sources(response):
    """Extract source URLs from Gemini grounding metadata."""
    sources = []
    try:
        metadata = response.candidates[0].grounding_metadata
        if metadata and metadata.grounding_chunks:
            for chunk in metadata.grounding_chunks:
                if chunk.web:
                    title = chunk.web.title or "Source"
                    uri = chunk.web.uri
                    if uri and uri not in [s[1] for s in sources]:
                        sources.append((title, uri))
    except (IndexError, AttributeError):
        pass
    return sources


def generate_section(client, section_name, prompt):
    """Generate one report section using Gemini with Google Search grounding."""
    print(f"  Generating: {section_name}...")

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )

            text = response.text or ""
            text = re.sub(r"^```html?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
            text = text.strip()

            if not text:
                print(f"  Empty response for {section_name}, retrying...")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(5)
                continue

            # Append grounding sources if the model didn't include inline links
            if "<a href" not in text.lower():
                sources = extract_grounding_sources(response)
                if sources:
                    links = " | ".join(
                        f'<a href="{uri}" target="_blank">{html_mod.escape(title)}</a>'
                        for title, uri in sources[:6]
                    )
                    text += f'\n<p><em>Sources: {links}</em></p>'

            print(f"  Done: {section_name}")
            return text

        except Exception as e:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(10 * (attempt + 1))

    print(f"  FAILED: {section_name} after {MAX_RETRIES} attempts")
    return (
        f"<h2>{section_name}</h2>\n"
        f"<p><em>This section could not be generated at this time.</em></p>"
    )


def build_section_prompts(date_str):
    base = (
        f"Today is {date_str}. "
        "You are writing one section of a daily news briefing. "
        "Output ONLY raw HTML — no markdown code fences, no ```html blocks, no <html>/<head>/<body> tags. "
        "Use <h2> for the section heading, <h3> for story headings, <p> for paragraphs. "
        'Include source links as <a href="URL" target="_blank">Source Name</a> after each story. '
        "Write concisely — aim for a 2-minute read for this section.\n\n"
    )

    return [
        (
            "Federal Politics",
            base
            + "Section: Federal Politics\n\n"
            "Search for and summarize the top 3–5 US federal political stories from today or the past 24 hours. "
            "Cover congressional activity, executive branch news, and Supreme Court developments as applicable.\n\n"
            "Guidelines:\n"
            "- Bipartisan, factual tone — present both perspectives where relevant\n"
            "- Avoid partisan framing or editorializing\n"
            "- Each story should have a descriptive <h3> heading\n"
            "- Include source links for each story",
        ),
        (
            "Tennessee & Nashville Politics",
            base
            + "Section: Tennessee & Nashville Politics\n\n"
            "Search for and cover local and state political news in three tiers:\n\n"
            "1. LEAD with Nashville-specific news — city council decisions, local policy, urban development, Metro government\n"
            "2. Follow with statewide Tennessee news — state legislature, governor's office, major state issues\n"
            "3. Close with 1–2 notable political stories from other US states worth knowing about\n\n"
            "Guidelines:\n"
            "- Bipartisan framing throughout\n"
            "- If Nashville-specific news is light today, note that and expand the state or other-states sections\n"
            "- Include source links for each story",
        ),
        (
            "World Politics",
            base
            + "Section: World Politics (US Relations Focus)\n\n"
            "Search for and summarize 3–4 major international stories from today or the past 24 hours. "
            "Emphasize stories related to US foreign policy and international relations.\n\n"
            "Guidelines:\n"
            "- Lead with the most significant story for a US audience\n"
            "- Cover diplomatic developments, conflicts, trade, and international agreements\n"
            "- Provide enough context for someone not following each story closely\n"
            "- Include source links for each story",
        ),
        (
            "AI & Technology",
            base
            + "Section: AI & Technology News\n\n"
            "Search for and summarize the top 3–4 stories in AI and technology from the past 24 hours.\n\n"
            "Cover:\n"
            "- Notable AI model releases or updates (OpenAI, Anthropic, Google DeepMind, Meta AI, etc.)\n"
            "- Major tech company news and product launches\n"
            "- AI policy and regulation developments\n"
            "- Significant research breakthroughs\n\n"
            "Guidelines:\n"
            "- Flag anything with direct consumer impact (new tools, product launches, safety news)\n"
            "- Neutral framing on policy/regulatory stories\n"
            "- Include source links for each story",
        ),
        (
            "Sports",
            base
            + "Section: Sports\n\n"
            "Search for sports news and cover the following:\n\n"
            "PRIMARY (always include if any news exists):\n"
            "- Tottenham Hotspur (Premier League) — match results, injury news, transfers, standings updates\n"
            "- Nashville SC (MLS) — match results, standings, roster news\n\n"
            "SECONDARY:\n"
            "- Assess which major US professional leagues (NBA, MLB, NFL, NHL) are most active or newsworthy today. "
            "Include a brief roundup of the top stories from up to 2–3 leagues. "
            "Focus on playoffs, major trades, records, and standout performances.\n\n"
            "Guidelines:\n"
            "- Lead with Tottenham Hotspur and Nashville SC sections\n"
            "- Include scores, standings context, and upcoming fixtures where relevant\n"
            "- Include source links",
        ),
    ]


def build_html_page(date_str, sections_html):
    nav_ids = [
        ("federal-politics", "Federal Politics"),
        ("tennessee-and-nashville-politics", "Tennessee & Nashville"),
        ("world-politics", "World Politics"),
        ("ai-and-technology", "AI & Technology"),
        ("sports", "Sports"),
    ]

    sections_combined = "\n\n".join(
        f'<section id="{nav_ids[i][0]}">\n{html}\n</section>'
        for i, (_, html) in enumerate(sections_html)
    )

    nav_links = "\n".join(
        f'            <li><a href="#{sid}">{label}</a></li>' for sid, label in nav_ids
    )

    timestamp = datetime.now(CENTRAL_TZ).strftime("%I:%M %p CT")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily News Report — {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: Georgia, 'Times New Roman', serif;
            max-width: 780px;
            margin: 0 auto;
            padding: 24px 20px;
            line-height: 1.75;
            color: #1a1a1a;
            background: #fdfdfd;
        }}
        header {{
            margin-bottom: 2.5em;
            padding-bottom: 1em;
            border-bottom: 3px solid #222;
        }}
        header h1 {{
            font-size: 2em;
            letter-spacing: -0.5px;
            margin-bottom: 4px;
        }}
        .date {{
            color: #555;
            font-style: italic;
            font-size: 1.05em;
        }}
        nav {{
            margin: 1.5em 0 2em;
            padding: 1em;
            background: #f5f5f5;
            border-radius: 6px;
        }}
        nav p {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.85em;
            color: #444;
            margin-bottom: 6px;
            font-weight: 600;
        }}
        nav ul {{
            list-style: none;
            display: flex;
            flex-wrap: wrap;
            gap: 8px 16px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            font-size: 0.9em;
        }}
        nav a {{ color: #2a5db0; text-decoration: none; }}
        nav a:hover {{ text-decoration: underline; }}
        section {{
            margin-bottom: 2.5em;
            padding-bottom: 1.5em;
            border-bottom: 1px solid #e0e0e0;
        }}
        section:last-child {{ border-bottom: none; }}
        h2 {{
            font-size: 1.5em;
            color: #222;
            margin-bottom: 0.6em;
            padding-bottom: 6px;
            border-bottom: 2px solid #e0e0e0;
        }}
        h3 {{
            font-size: 1.15em;
            color: #333;
            margin: 1.3em 0 0.4em;
        }}
        p {{ margin-bottom: 0.8em; }}
        a {{ color: #2a5db0; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        ul, ol {{ margin: 0.5em 0 1em 1.5em; }}
        li {{ margin-bottom: 0.3em; }}
        .sources {{
            font-size: 0.85em;
            color: #666;
            margin-top: 0.5em;
        }}
        footer {{
            margin-top: 3em;
            padding-top: 1em;
            border-top: 2px solid #222;
            color: #888;
            font-size: 0.85em;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        }}
        @media (max-width: 600px) {{
            body {{ padding: 16px 14px; font-size: 15px; }}
            header h1 {{ font-size: 1.6em; }}
            h2 {{ font-size: 1.3em; }}
            nav ul {{ flex-direction: column; gap: 6px; }}
        }}
    </style>
</head>
<body>
    <header>
        <h1>Daily News Report</h1>
        <p class="date">{date_str}</p>
    </header>
    <nav>
        <p>Sections</p>
        <ul>
{nav_links}
        </ul>
    </nav>
    <main>
        {sections_combined}
    </main>
    <footer>
        <p>Generated at {timestamp} using Gemini AI with Google Search</p>
    </footer>
</body>
</html>"""


def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    date_str = get_date_str()

    print("=== Daily News Report Generator ===")
    print(f"Date: {date_str}\n")

    section_prompts = build_section_prompts(date_str)
    sections_html = []

    for name, prompt in section_prompts:
        section_html = generate_section(client, name, prompt)
        sections_html.append((name, section_html))

    print("\nBuilding HTML page...")
    page_html = build_html_page(date_str, sections_html)

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "index.html").write_text(page_html, encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Report saved to {OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
