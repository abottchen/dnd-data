#!/usr/bin/env python3
"""Render a chapter draft (story.md) as a single-page reading view for DM review.

Usage: md2review.py STORY.md REVIEW.html --session N
The page uses the chronicle site's palette and typefaces and is meant to be
published as a private artifact for comments.
"""
import argparse
import html
import re

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("src")
ap.add_argument("dst")
ap.add_argument("--session", type=int, required=True)
args = ap.parse_args()
src, dst, session = args.src, args.dst, args.session
lines = open(src, encoding='utf-8').read().split('\n')

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', s)
    return s

title = None
body = []
i = 0
# title
while i < len(lines) and not lines[i].startswith('# '):
    i += 1
title = lines[i][2:].strip(); i += 1
# older drafts carried italic header lines and a --- rule after the title; skip them, render nothing
while i < len(lines) and (not lines[i].strip() or lines[i].strip() == '---' or re.fullmatch(r'\*[^*]+\*', lines[i].strip())):
    i += 1
para = []
def flush():
    global para
    if para:
        body.append('<p>' + inline(' '.join(para)) + '</p>')
        para = []
for l in lines[i:]:
    s = l.rstrip()
    if s.startswith('## '):
        flush()
        m = re.match(r'## ([IVXL]+)\. (.*)', s)
        if m:
            body.append(f'<h2><span class="num">{m.group(1)}</span>{inline(m.group(2))}</h2>')
        else:
            body.append(f'<h2>{inline(s[3:])}</h2>')
    elif s.strip() == '':
        flush()
    elif s.strip() == '*V.G.*':
        flush()
        body.append('<p class="sign"><em>V.G.</em></p>')
    else:
        para.append(s.strip())
flush()

page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=EB+Garamond:ital,wght@0,400;0,500;1,400&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {{
  /* single-theme reading page in the chronicle site's own palette; one 65ch column of body text */
  --ink: #14110E;
  --ink-warm: #241d15;
  --paper: #e8dcc3;
  --paper-dim: #9a8f7a;
  --brass: #B8894A;
  --brass-hi: #d6a460;
  --seal: #a73a2c;
  --rule: rgba(184, 137, 74, 0.22);
  --rule-strong: rgba(184, 137, 74, 0.5);
  --font-display: 'Cormorant Garamond', Georgia, serif;
  --font-body: 'EB Garamond', Georgia, serif;
  --font-label: 'IBM Plex Sans', system-ui, sans-serif;
  color-scheme: dark;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; }}
body {{
  background: var(--ink);
  color: var(--paper);
  font-family: var(--font-body);
  font-size: 1.1875rem;
  line-height: 1.6;
  padding: clamp(24px, 6vw, 72px) 16px 96px;
}}
.chapter {{ max-width: 65ch; margin: 0 auto; }}
.eyebrow {{
  font-family: var(--font-label);
  font-size: 0.75rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--brass);
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}}
.eyebrow .draft {{
  color: var(--seal);
  border: 1px solid var(--seal);
  padding: 2px 8px;
  border-radius: 2px;
}}
h1 {{
  font-family: var(--font-display);
  font-weight: 500;
  font-size: clamp(2.2rem, 6vw, 3.4rem);
  line-height: 1.05;
  margin: 18px 0 24px;
  text-wrap: balance;
  color: var(--paper);
}}
.body {{ padding-top: 28px; }}
.body p {{ margin: 0 0 1.15em; }}
.body p + p {{ text-indent: 1.4em; margin-top: -0.35em; }}
.body h2 {{
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 1.75rem;
  line-height: 1.15;
  margin: 2.4em 0 0.9em;
  padding-top: 1.2em;
  border-top: 1px solid var(--rule);
  text-wrap: balance;
  color: var(--brass-hi);
}}
.body h2 .num {{
  font-family: var(--font-label);
  font-size: 0.75rem;
  letter-spacing: 0.18em;
  color: var(--brass);
  display: block;
  margin-bottom: 8px;
}}
.body h2 + p {{ text-indent: 0; margin-top: 0; }}
.body h2 + p::first-letter {{
  font-family: var(--font-display);
  font-size: 2.4em;
  line-height: 0.8;
  float: left;
  padding: 6px 8px 0 0;
  color: var(--brass-hi);
}}
.body p.sign {{
  text-indent: 0;
  text-align: right;
  color: var(--brass);
  font-size: 1.3rem;
  margin-top: 2em;
}}
em {{ font-style: italic; }}
.note {{
  margin-top: 64px;
  padding-top: 18px;
  border-top: 1px solid var(--rule);
  font-family: var(--font-label);
  font-size: 0.8rem;
  color: var(--paper-dim);
  line-height: 1.5;
}}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto; }} }}
</style>
</head>
<body>
<article class="chapter">
  <div class="eyebrow"><span>Chronicle of Chult</span><span>Session {session}</span><span class="draft">Draft for review</span></div>
  <h1>{html.escape(title)}</h1>
  <div class="body">
    {chr(10).join(body)}
  </div>
  <p class="note">Draft of the Chronicle entry for session {session}, rendered from {html.escape(src)}. Leave comments on this page or reply in the session with the section numeral and the phrase to change.</p>
</article>
</body>
</html>
'''
open(dst, 'w', encoding='utf-8').write(page)
print('wrote', dst, len(page), 'bytes;', len(body), 'blocks; title:', title)
