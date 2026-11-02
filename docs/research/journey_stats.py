import collections
import json
import os
import re
import sys
import zipfile

root = sys.argv[1]
zips = sorted(f for f in os.listdir(root) if f.endswith(".zip"))

entries = {}
dup_ids = 0
ext_count = collections.Counter()
ext_bytes = collections.Counter()
big = []
fmt = collections.Counter()
moods = collections.Counter()
types = collections.Counter()
tz = collections.Counter()
has = collections.Counter()
photos_field = collections.Counter()
per_zip = []
orphans = 0
missing = 0
max_text = 0
tag_set = collections.Counter()

re_html = re.compile(r"<(p|br|div|b|i|strong|em|ul|ol|li|h[1-6]|a|span|img)[\s>/]", re.I)
re_md = re.compile(r"(\*\*[^*]+\*\*|^#{1,6} |^\s*[-*] |^\s*\d+\. |\[[^\]]+\]\([^)]+\)|!\[)", re.M)

for zname in zips:
    z = zipfile.ZipFile(os.path.join(root, zname))
    infos = z.infolist()
    names = {i.filename for i in infos}
    n_entries = 0
    referenced = set()
    for i in infos:
        n = i.filename
        e = n.rsplit(".", 1)[-1].lower() if "." in n else ""
        if e != "json":
            ext_count[e] += 1
            ext_bytes[e] += i.file_size
            big.append((i.file_size, zname, e))
            continue
        d = json.loads(z.read(n))
        n_entries += 1
        eid = d.get("id")
        if eid in entries:
            dup_ids += 1
        entries[eid] = zname
        t = d.get("text") or ""
        max_text = max(max_text, len(t))
        if re_html.search(t):
            fmt["html"] += 1
        elif re_md.search(t):
            fmt["markdown-like"] += 1
        elif t:
            fmt["plain"] += 1
        else:
            fmt["empty"] += 1
        moods[d.get("mood")] += 1
        types[d.get("type")] += 1
        tz[d.get("timezone")] += 1
        if d.get("lat") not in (None, 0, 0.0, 1.7976931348623157e308):
            has["coords"] += 1
        if d.get("address"):
            has["address"] += 1
        w = d.get("weather") or {}
        if w.get("description") or w.get("degree_c") not in (None, 0, 0.0):
            has["weather"] += 1
        if d.get("tags"):
            has["tags"] += 1
            for tg in d["tags"]:
                tag_set[tg] += 1
        for k in ("favourite", "music_title", "label", "folder", "preview_text"):
            if d.get(k):
                has[k] += 1
        ph = d.get("photos") or []
        photos_field[len(ph) > 0] += 1
        for p in ph:
            referenced.add(p)
            if p not in names:
                missing += 1
    for i in infos:
        if not i.filename.endswith(".json") and i.filename not in referenced:
            orphans += 1
    per_zip.append((zname, n_entries, len(infos) - n_entries))

print("zips:", len(zips))
for row in per_zip:
    print("  %-26s entries=%5d attachments=%5d" % row)
print("unique entries:", len(entries), "dup ids across zips:", dup_ids)
print("text format:", dict(fmt), "max text len:", max_text)
print("attachments by ext:", {e: (ext_count[e], round(ext_bytes[e] / 2**30, 2)) for e in ext_count})
big.sort(reverse=True)
print("largest files (MB):", [(round(s / 2**20), z, e) for s, z, e in big[:8]])
print("moods:", dict(moods))
print("types:", dict(types))
print("timezones (top):", tz.most_common(8))
print("fields present:", dict(has))
print("entries with photos field:", dict(photos_field), "refs missing in zip:", missing, "files not referenced:", orphans)
print("distinct tags:", len(tag_set))
