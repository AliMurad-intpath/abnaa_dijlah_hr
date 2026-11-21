import functools
import html
import re
import threading
from pathlib import Path

import pymupdf

FONT_DIR = Path(__file__).resolve().parent / 'static' / 'fonts'

FONT_CSS = {
    'naskh': '* {font-family: sans-serif; margin: 0; padding: 0;}',
    'dejavu': """
@font-face {font-family: hrdoc; src: url(DejaVuSans.ttf);}
@font-face {font-family: hrdoc; src: url(DejaVuSans-Bold.ttf); font-weight: bold;}
* {font-family: hrdoc; margin: 0; padding: 0;}
""",
    # Times New Roman look-alike (Liberation Serif / Tinos metrics); DejaVu covers Arabic and symbols
    'times': """
@font-face {font-family: hrdoc; src: url(DejaVuSans.ttf);}
@font-face {font-family: hrdoc; src: url(DejaVuSans-Bold.ttf); font-weight: bold;}
@font-face {font-family: hrtimes; src: url(LiberationSerif-Regular.ttf);}
@font-face {font-family: hrtimes; src: url(LiberationSerif-Bold.ttf); font-weight: bold;}
@font-face {font-family: hrar; src: url(FreeSerifArabic-Regular.ttf);}
@font-face {font-family: hrar; src: url(FreeSerifArabic-Bold.ttf); font-weight: bold;}
* {font-family: hrtimes, hrar, hrdoc; margin: 0; padding: 0;}
""",
}
# A licensed copy of the real Times New Roman, if the company drops one in static/fonts, wins
# over the Liberation Serif look-alike (regular + bold, any of these file names).
_REAL_TIMES = {'regular': ('TimesNewRoman.ttf', 'times.ttf', 'Times New Roman.ttf'),
               'bold': ('TimesNewRoman-Bold.ttf', 'timesbd.ttf', 'Times New Roman Bold.ttf')}


def _real_times():
    found = {}
    for style, names in _REAL_TIMES.items():
        for name in names:
            if (FONT_DIR / name).is_file():
                found[style] = name
                break
    return found if len(found) == 2 else None


_TIMES = _real_times()
if _TIMES:
    FONT_CSS['times'] = FONT_CSS['times'].replace('LiberationSerif-Regular.ttf', _TIMES['regular']).replace(
        'LiberationSerif-Bold.ttf', _TIMES['bold'])

ARABIC_SCRIPT = 6                                               
                                                                             
_LOCK = threading.RLock()

def _locked(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _LOCK:
            return func(*args, **kwargs)
    return wrapper

@functools.cache
def _font_archive():
                                                                                     
    archive = pymupdf.Archive()
    for name in ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'LiberationSerif-Regular.ttf', 'LiberationSerif-Bold.ttf',
                 'FreeSerifArabic-Regular.ttf', 'FreeSerifArabic-Bold.ttf'):
        archive.add((FONT_DIR / name).read_bytes(), name)
    if _TIMES:
        for name in _TIMES.values():
            archive.add((FONT_DIR / name).read_bytes(), name)
    return archive

@_locked
def naskh_font_bytes():

    return pymupdf.Font(script=ARABIC_SCRIPT).buffer

RTL_CHARS = re.compile('[֐-ࣿיִ-﷿ﹰ-﻿]')
                                                                 
BLANK_MARKS = re.compile(r'^[\s().\[\]{}_:/\\|…\-–—·•○□☐]*$')
EDGE_TOLERANCE = 0.5
LINE_HEIGHT = 1.15
OVERLAP_RATIO = 0.3

class LayoutIssue(dict):
    """{'key', 'label', 'code': page|outside|overflow|image|overlap, 'message', 'blocking'}

    'overlap' (box covers text printed on the original form) is a designer
    warning only; every other code blocks submission."""

@_locked
def page_sizes(pdf_bytes):
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:
        return [(page.rect.width, page.rect.height) for page in doc]

@_locked
def render_page_png(pdf_bytes, page_number, zoom=1.5, items=None):

    if items:
        pdf_bytes, _issues = render(pdf_bytes, items, collect=True)
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:
        if not 1 <= page_number <= len(doc):
            raise ValueError('page out of range')
        return doc[page_number - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes('png')

ARABIC_RUN = re.compile('[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]'
                        '[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff\\s\u060c\u061b\u061f.,:()/\\d-]*')

def _arabic_in_document_font(body):
    """The fixed text of the forms is Times (Liberation Serif) for Latin and FreeSerif for Arabic. Pin Arabic runs
    to FreeSerif so filled-in values look the same instead of falling back to a different Arabic face."""
    return ARABIC_RUN.sub(lambda m: '<span style="font-family:hrar">%s</span>' % m.group(0), body)

def _html(item):
    text = str(item.get('text') or '')
    multiline = item.get('multiline')
    if not multiline:
        text = ' '.join(text.split())
    rtl = bool(RTL_CHARS.search(text))
    align = item.get('align') or ('right' if rtl else 'left')
    body = '<br/>'.join(html.escape(line) for line in text.splitlines()) if multiline else html.escape(text)
    if item.get('font') != 'naskh' and not _TIMES:
        body = _arabic_in_document_font(body)
    style = 'font-size:%.2fpt; line-height:%.2f; text-align:%s; font-weight:%s; white-space:%s;' % (
        float(item.get('font_size') or 11), LINE_HEIGHT, align,
        'bold' if item.get('bold') else 'normal', 'normal' if multiline else 'nowrap')
    return '<div dir="%s" style="%s">%s</div>' % ('rtl' if rtl else 'ltr', style, body)

def _fit(rect, markup, scale_low, css, archive):

    with pymupdf.open() as scratch:
        page = scratch.new_page(width=rect.width + 2, height=rect.height + 2)
        spare, scale = page.insert_htmlbox(pymupdf.Rect(0, 0, rect.width, rect.height), markup,
                                           css=css, archive=archive, scale_low=scale_low)
    return None if spare < 0 else (spare, scale)

@_locked
def frames(pdf_bytes):

    result = []
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:
        for page in doc:
            found = set()
            for drawing in page.get_drawings():
                rect = (drawing['rect'] * page.rotation_matrix).normalize()
                if 10 <= rect.width <= page.rect.width * 0.9 and 8 <= rect.height <= 120:
                    found.add(tuple(round(v, 1) for v in (rect.x0, rect.y0, rect.width, rect.height)))
            result.append(sorted(found, key=lambda r: (r[1], r[0])))
    return result

@_locked
def overlap_issues(pdf_bytes, items):

    issues = []
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:
        words = {}
        for item in items:
            number = int(item.get('page') or 1)
            if not 1 <= number <= len(doc):
                continue
            if number not in words:
                page = doc[number - 1]
                words[number] = [(pymupdf.Rect(w[:4]) * page.rotation_matrix, w[4])
                                 for w in page.get_text('words') if not BLANK_MARKS.match(w[4])]
            box = pymupdf.Rect(item['x'], item['y'], item['x'] + item['width'], item['y'] + item['height'])
            covered = [text for rect, text in words[number]
                       if rect.get_area() and (rect & box).get_area() / rect.get_area() >= OVERLAP_RATIO]
            if covered:
                issues.append(LayoutIssue(key=item.get('key'), label=item.get('label') or '?', code='overlap',
                                          blocking=False, message='covers printed text: %s' % ' '.join(covered[:6])))
    return issues

@_locked
def render(pdf_bytes, items, collect=False, output=True):

    archive = _font_archive()
    issues = []
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:

        surfaces = []
        for page in doc:
            area, inverse_rotation = page.rect, page.derotation_matrix
            crop, rotation = page.cropbox, page.rotation
            page.set_rotation(0)
            original_transform = page.transformation_matrix
            media = page.mediabox
            page.set_cropbox(pymupdf.Rect(media.x0, 0, media.x1, media.height))
            adjustment = ~original_transform * page.transformation_matrix
            surfaces.append((area, inverse_rotation, adjustment, crop, rotation))
        for item in items:
            label = item.get('label') or item.get('key') or '?'
            number = int(item.get('page') or 1)
            if not 1 <= number <= len(doc):
                issues.append(LayoutIssue(key=item.get('key'), label=label, code='page',
                                          message='page %s does not exist (document has %s)' % (number, len(doc))))
                continue
            page = doc[number - 1]
            box = pymupdf.Rect(item['x'], item['y'], item['x'] + item['width'], item['y'] + item['height'])
            area, inverse_rotation, adjustment, _crop, rotation = surfaces[number - 1]
            if (box.width <= 0 or box.height <= 0 or box.x0 < -EDGE_TOLERANCE or box.y0 < -EDGE_TOLERANCE
                    or box.x1 > area.width + EDGE_TOLERANCE or box.y1 > area.height + EDGE_TOLERANCE):
                issues.append(LayoutIssue(key=item.get('key'), label=label, code='outside', message=(
                    'box x=%.0f y=%.0f w=%.0f h=%.0f exceeds page %s (%.0f x %.0f pt)' % (
                        box.x0, box.y0, box.width, box.height, number, area.width, area.height))))
                continue
                                                                                   
            target = (box * inverse_rotation * adjustment).normalize()
            if item.get('kind') == 'image':
                if item.get('image'):
                    try:
                        page.insert_image(target, stream=item['image'], keep_proportion=True,
                                          rotate=rotation, overlay=True)
                    except Exception as exc:                      
                        issues.append(LayoutIssue(key=item.get('key'), label=label, code='image', message=str(exc)))
                continue
            if not str(item.get('text') or '').strip():
                continue
            font_size = float(item.get('font_size') or 11)
            min_size = min(font_size, max(4.0, float(item.get('min_font_size') or font_size)))
            markup = _html(item)
            css = FONT_CSS.get(item.get('font'), FONT_CSS['times'])
            fit = _fit(box, markup, min_size / font_size, css, archive)
            if fit is None:
                issues.append(LayoutIssue(key=item.get('key'), label=label, code='overflow', message=(
                    'text does not fit in %.0f x %.0f pt even at %.1f pt' % (box.width, box.height, min_size))))
                continue
            spare, _scale = fit
                                                                                           
            if not item.get('multiline') and spare > 0:
                box = pymupdf.Rect(box.x0, box.y0 + spare / 2, box.x1, box.y1)
                target = (box * inverse_rotation * adjustment).normalize()
            if output:
                page.insert_htmlbox(target, markup, css=css, archive=archive,
                                    scale_low=min_size / font_size, rotate=rotation)
        for page, (_area, _inverse, _adjustment, crop, rotation) in zip(doc, surfaces):
            page.set_cropbox(crop)
            page.set_rotation(rotation)
        if not output:
            return None, issues
        doc.subset_fonts()
        data = doc.tobytes(garbage=3, deflate=True)
    return data, issues
