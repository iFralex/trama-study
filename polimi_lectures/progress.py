import re


def recording_bytes(title):
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(KB|MB|GB)\b', title, re.I)
    if not match:
        return None
    return int(float(match[1].replace(',', '.')) * {'KB': 1000, 'MB': 1000000, 'GB': 1000000000}[match[2].upper()])


class BatchProgress:
    """Bytes available for the selected batch; listing sizes remain estimates."""
    def __init__(self, rows):
        self.sizes = {}
        self.done = {}
        self.exact = set()
        self.completed = set()
        self.current = None
        for row in rows:
            key = (row['course'], row['id'])
            self.sizes[key] = (row['size_bytes'] if 'size_bytes' in row.keys() else None) or recording_bytes(row['title'])
            self.done[key] = 0

    def start(self, row):
        self.current = (row['course'], row['id'])

    def report(self, size, total):
        self.done[self.current] = size
        if total:
            self.sizes[self.current] = total
            self.exact.add(self.current)

    def finish(self, size):
        self.report(size, size)
        self.completed.add(self.current)

    def text(self):
        size = sum(self.done.values())
        count = '%d/%d lezioni' % (len(self.completed), len(self.sizes))
        if any(value is None for value in self.sizes.values()):
            return 'Totale: %.1f MB · dimensione totale da determinare · %s' % (size / 1000000, count)
        total = sum(max(value, self.done[key]) for key, value in self.sizes.items())
        complete = len(self.completed) == len(self.sizes)
        percent = 100 if complete else min(99, int(size * 100 / total)) if total else 0
        estimate = '≈ ' if len(self.exact) < len(self.sizes) else ''
        return 'Totale: %s%d%% · %.1f / %s%.1f MB · %s' % (estimate, percent, size / 1000000, estimate, total / 1000000, count)
