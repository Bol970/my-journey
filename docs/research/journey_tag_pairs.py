import collections
import json
import os
import sys
import zipfile

# Usage: python3 -I journey_tag_pairs.py <zip-dir> <out-file> <anchor-tag> [<anchor-tag> ...]
# Anchor tags are the frequent "section" tags whose co-occurrence with other tags is measured.
root, out = sys.argv[1], sys.argv[2]
ANCHORS = sys.argv[3:]
if not ANCHORS:
    sys.exit("pass at least one anchor tag")

count = collections.Counter()
with_anchor = collections.defaultdict(collections.Counter)
anchor_sets = collections.Counter()
pairs = collections.Counter()

for zname in sorted(f for f in os.listdir(root) if f.endswith(".zip")):
    z = zipfile.ZipFile(os.path.join(root, zname))
    for n in z.namelist():
        if not n.endswith(".json"):
            continue
        tags = set(json.loads(z.read(n)).get("tags") or [])
        anchors = tuple(a for a in ANCHORS if a in tags)
        anchor_sets[anchors] += 1
        rest = sorted(tags - set(ANCHORS))
        for t in rest:
            count[t] += 1
            with_anchor[t][anchors] += 1
        for i, a in enumerate(rest):
            for b in rest[i + 1:]:
                pairs[(a, b)] += 1

with open(out, "w") as f:
    f.write("== entries by anchor combination ==\n")
    for k, v in anchor_sets.most_common():
        f.write("%s\t%d\n" % ("+".join(k) or "(none)", v))
    f.write("\n== non-anchor tags (uses>=3): uses, anchor split ==\n")
    for t, c in count.most_common():
        if c < 3:
            break
        split = ", ".join("%s:%d" % ("+".join(k) or "-", v) for k, v in with_anchor[t].most_common())
        f.write("%d\t%s\t%s\n" % (c, t, split))
    f.write("\n== frequent non-anchor pairs ==\n")
    for (a, b), c in pairs.most_common(40):
        f.write("%d\t%s + %s\n" % (c, a, b))
print("done")
