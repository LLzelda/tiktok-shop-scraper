#!/usr/bin/env python3
"""
Read categories.csv[id,name]  ➜  emit third_categories.csv[id,slug,url]
"""
import re, pandas as pd, argparse, unicodedata, textwrap, csv
from pathlib import Path

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")

def main(infile: Path, outfile: Path):
    df = pd.read_csv(infile)
    # heuristics: third-level categories have an id ≥ 800000 (adjust if needed)
    third = df[df["id"] >= 800000].copy()
    third["slug"] = third["name"].apply(slugify)
    third["url"]  = ("https://www.tiktok.com/shop/c/" +
                     third["slug"] + "/" + third["id"].astype(str))
    third[["id", "slug", "url"]].to_csv(outfile, index=False)
    print(f"✓  {len(third):,} third-level URLs → {outfile}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile",  type=Path, default=Path("categories.csv"))
    ap.add_argument("--outfile", type=Path, default=Path("third_categories.csv"))
    main(**vars(ap.parse_args()))
