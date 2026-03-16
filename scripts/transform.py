import os, json, sys
out = "data"; os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "commissioners.csv"), "w") as f:
    f.write("smd,anc,name,email,term_start,term_end\n6B02,6B,Jane Doe,jane@example.org,2025-01-01,2026-12-31\n")
with open(os.path.join(out, "smds.geojson"), "w") as f:
    json.dump({"type":"FeatureCollection","features":[]}, f)
print("transform: wrote placeholder data")
