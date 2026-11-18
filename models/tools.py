"""Pure-python helpers used by the printed forms."""
import base64
import os
from datetime import date, datetime

from markupsafe import Markup, escape

MONTHS_AR = ['كانون الثاني', 'شباط', 'آذار', 'نيسان', 'أيار', 'حزيران',
             'تموز', 'آب', 'أيلول', 'تشرين الأول', 'تشرين الثاني', 'كانون الأول']
NBSP = ' '


def _as_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def d3(value):
    d = _as_date(value)
    if not d:
        return Markup('<span class="ad-d">%s/%s/%s202</span>' % (NBSP * 4, NBSP * 4, NBSP))
    return Markup('<span class="ad-d">%02d / %02d / %04d</span>' % (d.day, d.month, d.year))


def month_year_ar(value):
    d = _as_date(value)
    if not d:
        return Markup(NBSP)
    return Markup('%s %s/' % (MONTHS_AR[d.month - 1], d.year))


def box(flag):
    return Markup('<span class="ad-box%s"></span>' % (' on' if flag else ''))


def money(value):
    if value in (None, False, ''):
        return ''
    try:
        return '{:,.0f}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def dots(value, mm=40):
    text = escape(value) if value not in (None, False) else ''
    return Markup('<span class="ad-dots" style="min-width:%smm">%s</span>' % (mm, text or NBSP))


def txt(value):
    return escape(value) if value not in (None, False) else ''


def get(rec, *names):
    for name in names:
        try:
            val = getattr(rec, name)
        except AttributeError:
            continue
        if val:
            return val
    return ''


def logo_data_uri(full=False):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'static', 'img', 'ad_logo_full.png' if full else 'ad_logo.png')
    try:
        with open(path, 'rb') as fh:
            return 'data:image/png;base64,' + base64.b64encode(fh.read()).decode()
    except OSError:
        return ''
