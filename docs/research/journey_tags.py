import collections
import json
import os
import re
import sys
import zipfile

root, out = sys.argv[1], sys.argv[2]

count = collections.Counter()
first_year = {}
last_year = {}
per_entry = collections.Counter()

for zname in sorted(f for f in os.listdir(root) if f.endswith(".zip")):
    z = zipfile.ZipFile(os.path.join(root, zname))
    for n in z.namelist():
        if not n.endswith(".json"):
            continue
        d = json.loads(z.read(n))
        tags = d.get("tags") or []
        per_entry[len(tags)] += 1
        year = int(re.search(r"(\d{4})", zname).group(1))
        for t in tags:
            count[t] += 1
            first_year[t] = min(first_year.get(t, year), year)
            last_year[t] = max(last_year.get(t, year), year)


def norm(t):
    t = t.strip().lstrip("#").lower().replace("ё", "е")
    return re.sub(r"[\s_\-./:]+", " ", t).strip()


collisions = collections.defaultdict(list)
for t in count:
    collisions[norm(t)].append(t)
collisions = {k: v for k, v in collisions.items() if len(v) > 1}

seps = collections.Counter()
for t in count:
    for s, name in ((" ", "space"), ("-", "dash"), ("_", "underscore"), ("/", "slash"), (":", "colon"), (".", "dot"), ("#", "hash")):
        if s in t.strip():
            seps[name] += 1

first_word = collections.Counter()
first_word_uses = collections.Counter()
for t, c in count.items():
    words = norm(t).split()
    if len(words) > 1:
        first_word[words[0]] += 1
        first_word_uses[words[0]] += c

with open(out, "w") as f:
    f.write("distinct tags: %d\n" % len(count))
    f.write("tags per entry: %s\n" % sorted(per_entry.items()))
    f.write("used once: %d, used <=3: %d\n" % (sum(1 for c in count.values() if c == 1), sum(1 for c in count.values() if c <= 3)))
    f.write("separators (tags containing): %s\n" % dict(seps))
    f.write("multi-word tags: %d\n" % sum(1 for t in count if len(norm(t).split()) > 1))
    f.write("\n== first word of multi-word tags (distinct tags, total uses) ==\n")
    for w, c in first_word.most_common(60):
        f.write("%s\t%d\t%d\n" % (w, c, first_word_uses[w]))
    f.write("\n== normalization collisions ==\n")
    for k, v in sorted(collisions.items()):
        f.write("%s <- %s\n" % (k, " | ".join("%s(%d)" % (x, count[x]) for x in v)))
    f.write("\n== all tags by uses: uses, first-last year, tag ==\n")
    for t, c in count.most_common():
        f.write("%d\t%d-%d\t%s\n" % (c, first_year[t], last_year[t], t))
print("done", len(count))
