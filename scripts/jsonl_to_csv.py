from __future__ import annotations
import csv
import json
from pathlib import Path

def main():
    import argparse
    ap = argparse.ArgumentParser(description='Convert JSONL to CSV with selected fields')
    ap.add_argument('--input', required=True, help='Path to input .jsonl')
    ap.add_argument('--output', required=True, help='Path to output .csv')
    ap.add_argument('--fields', required=True, help='Comma-separated list of fields to include, in order')
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    fields = [f.strip() for f in args.fields.split(',') if f.strip()]
    if not fields:
        raise SystemExit('No fields provided')

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with in_path.open('r', encoding='utf-8') as fin, out_path.open('w', encoding='utf-8', newline='') as fout:
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()
        for line in fin:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            row = {k: obj.get(k, '') for k in fields}
            writer.writerow(row)
    print(f'Done: wrote {out_path} with fields={fields}')

if __name__ == '__main__':
    main()
