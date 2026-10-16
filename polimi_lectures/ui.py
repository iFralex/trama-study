import os
import re
from datetime import date


def detail(message):
    if os.environ.get('POLIMI_LECTURES_QUIET') != '1':
        print(message, flush=True)


def course_name(label):
    label = re.sub(r'^\d+\s*-\s*', '', label)
    label = re.sub(r'\s*\([^)]*\)', '', label)
    return re.sub(r'\s*\[(20\d{2}[-/]\d{2,4})\]', r' · \1', label).strip()


def lesson_name(title):
    original = title
    title = re.sub(r'^\d{1,2}[/.]\d{1,2}[/.]\d{4}\s+\d{1,2}:\d{2}\s*', '', title)
    title = re.sub(r'^.*?\b(?:Lezione|Esercitazione|Laboratorio|Altro)\b\s*', '', title, flags=re.I)
    title = re.sub(r'^.*?Personal Room-\d{8}\s+\d{4}(?:-\d+)?[.\s]*', '', title, flags=re.I)
    title = re.sub(r'\s+\d+\s*min\s+[\d.,]+\s*(?:MB|GB)\s*$', '', title, flags=re.I).strip()
    title = title or original
    return title if len(title) <= 100 else title[:97] + '…'


def show_date(value):
    return date.fromisoformat(value).strftime('%d/%m/%Y') if value else 'Data sconosciuta'
