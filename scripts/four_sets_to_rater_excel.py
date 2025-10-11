from __future__ import annotations
import argparse
import csv
import xlsxwriter


SETS = [
    ("Rate - Flash CoT", "cot_output_flash"),
    ("Rate - Flash Minimal", "minimal_output_flash"),
    ("Rate - FlashLite CoT", "cot_output_flash_lite"),
    ("Rate - FlashLite Minimal", "minimal_output_flash_lite"),
]


def write_sheet(ws, wb, headers, rows, json_col):
    # Formats
    header_fmt = wb.add_format({'bold': True, 'text_wrap': True, 'valign': 'top'})
    wrap_fmt = wb.add_format({'text_wrap': True, 'valign': 'top'})

    # Build rating headers
    base_cols = [
        'id', 'source_text', 'output', 'json_ok', 'num_options_ok', 'answer_in_context',
        'accuracy', 'fluency', 'pedagogy', 'distractor', 'hallucination', 'prefer', 'comments', 'rater_id'
    ]
    ws.write_row(0, 0, base_cols, header_fmt)

    # Map helper to check columns present
    json_ok_col = f"{json_col}_json_ok"
    num_ok_col = f"{json_col}_num_options_ok"
    aic_col = f"{json_col}_answer_in_context"

    # Write data rows
    for r_idx, r in enumerate(rows, start=1):
        out = r.get(json_col, '')
        ws.write(r_idx, 0, r.get('id', ''), wrap_fmt)
        ws.write(r_idx, 1, r.get('source_text', ''), wrap_fmt)
        ws.write(r_idx, 2, out, wrap_fmt)
        ws.write(r_idx, 3, r.get(json_ok_col, ''), wrap_fmt)
        ws.write(r_idx, 4, r.get(num_ok_col, ''), wrap_fmt)
        ws.write(r_idx, 5, r.get(aic_col, ''), wrap_fmt)
        # rating columns left blank for raters (indices 6..12), rater_id at 13

    # Freeze, filter, sizes
    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, len(rows), len(base_cols)-1)
    for c in range(len(base_cols)):
        ws.set_column(c, c, 60)
    ws.set_row(0, 24)
    for r in range(1, len(rows)+1):
        ws.set_row(r, 90)

    # Data validation
    # accuracy/fluency/pedagogy: 1-5
    for r in range(1, len(rows)+1):
        for c in (6, 7, 8):
            ws.data_validation(r, c, r, c, {
                'validate': 'list', 'source': ['1','2','3','4','5']
            })
        # distractor/hallucination as 0/1 (0=no issue, 1=has issue)
        for c in (9, 10):
            ws.data_validation(r, c, r, c, {
                'validate': 'list', 'source': ['0','1']
            })
        # prefer: free text or choose Yes/No (for this set); leave free form


def write_guide(ws, wb):
    text = (
        "Instructions for Raters:\n\n"
        "- One sheet per output set: Flash CoT, Flash Minimal, FlashLite CoT, FlashLite Minimal.\n"
        "- Columns:\n"
        "  id: sample id\n"
        "  source_text: original context\n"
        "  output: pretty JSON of the generated MCQ/fill\n"
        "  json_ok / num_options_ok / answer_in_context: automatic checks (1=pass, 0=fail)\n"
        "  accuracy/fluency/pedagogy: rate 1–5 (1=poor, 5=excellent)\n"
        "  distractor/hallucination: 0 or 1 (0=no issue, 1=issue)\n"
        "  prefer: optional free-text (e.g., 'prefer this set for the item')\n"
        "  comments: notes\n"
        "  rater_id: your identifier\n\n"
        "Note: 'answer_in_context' is a lexical heuristic; not a final quality signal."
    )
    wrap = wb.add_format({'text_wrap': True, 'valign': 'top'})
    ws.write(0, 0, text, wrap)
    ws.set_column(0, 0, 120)
    ws.set_row(0, 200)


def main(input_csv: str, output_xlsx: str):
    with open(input_csv, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    wb = xlsxwriter.Workbook(output_xlsx)

    # Guide sheet
    guide = wb.add_worksheet('Guide')
    write_guide(guide, wb)

    # Per-set rater sheets
    for title, json_col in SETS:
        ws = wb.add_worksheet(title[:31])  # Excel sheet name limit
        write_sheet(ws, wb, headers, rows, json_col)

    # Also include a Summary sheet (first 200 chars of output to keep sheet light)
    summ = wb.add_worksheet('Summary')
    header_fmt = wb.add_format({'bold': True, 'text_wrap': True, 'valign': 'top'})
    wrap_fmt = wb.add_format({'text_wrap': True, 'valign': 'top'})
    summ_headers = ['id','source_text','flash_cot','flash_min','lite_cot','lite_min']
    summ.write_row(0, 0, summ_headers, header_fmt)
    for i, r in enumerate(rows, start=1):
        def trunc(s: str) -> str:
            s = s or ''
            return (s[:200] + '...') if len(s) > 200 else s
        summ.write(i, 0, r.get('id',''), wrap_fmt)
        summ.write(i, 1, r.get('source_text',''), wrap_fmt)
        summ.write(i, 2, trunc(r.get('cot_output_flash','')), wrap_fmt)
        summ.write(i, 3, trunc(r.get('minimal_output_flash','')), wrap_fmt)
        summ.write(i, 4, trunc(r.get('cot_output_flash_lite','')), wrap_fmt)
        summ.write(i, 5, trunc(r.get('minimal_output_flash_lite','')), wrap_fmt)
    summ.freeze_panes(1,0)
    summ.autofilter(0,0,len(rows),len(summ_headers)-1)
    for c in range(len(summ_headers)):
        summ.set_column(c, c, 40)
    summ.set_row(0, 24)
    for r in range(1, len(rows)+1):
        summ.set_row(r, 60)

    # Totals sheet: aggregate metrics per set, by model, by prompt type, and overall
    totals = wb.add_worksheet('Totals')
    header_fmt = wb.add_format({'bold': True, 'text_wrap': True, 'valign': 'top'})
    num_fmt = wb.add_format({'num_format': '0.00'})

    totals_headers = ['group','n_rated','accuracy_avg','fluency_avg','pedagogy_avg','distractor_rate','hallucination_rate']
    totals.write_row(0, 0, totals_headers, header_fmt)

    # Helper to generate formulas
    last_row = len(rows) + 1  # header is row 1, data rows 2..last_row
    def rng(sheet: str, col: str) -> str:
        return f"'{sheet}'!{col}2:{col}{last_row}"

    # Rows definitions: label + list of source sheets to combine
    groups = [
        ('Flash CoT',            ['Rate - Flash CoT']),
        ('Flash Minimal',        ['Rate - Flash Minimal']),
        ('FlashLite CoT',        ['Rate - FlashLite CoT']),
        ('FlashLite Minimal',    ['Rate - FlashLite Minimal']),
        ('Flash (model)',        ['Rate - Flash CoT','Rate - Flash Minimal']),
        ('FlashLite (model)',    ['Rate - FlashLite CoT','Rate - FlashLite Minimal']),
        ('CoT (prompt)',         ['Rate - Flash CoT','Rate - FlashLite CoT']),
        ('Minimal (prompt)',     ['Rate - Flash Minimal','Rate - FlashLite Minimal']),
        ('All',                  ['Rate - Flash CoT','Rate - Flash Minimal','Rate - FlashLite CoT','Rate - FlashLite Minimal']),
    ]

    # Column letters for rating fields on per-set sheets
    COL_ACC = 'G'; COL_FLU = 'H'; COL_PED = 'I'; COL_DIS = 'J'; COL_HAL = 'K'

    for i, (label, sheets) in enumerate(groups, start=1):
        row = i
        totals.write(row, 0, label)
        # n_rated = sum of COUNT of accuracy across sheets
        count_parts = [f"COUNT({rng(s, COL_ACC)})" for s in sheets]
        totals.write_formula(row, 1, '=' + '+'.join(count_parts))
        # averages/rates across combined ranges
        acc_ranges = ','.join(rng(s, COL_ACC) for s in sheets)
        flu_ranges = ','.join(rng(s, COL_FLU) for s in sheets)
        ped_ranges = ','.join(rng(s, COL_PED) for s in sheets)
        dis_ranges = ','.join(rng(s, COL_DIS) for s in sheets)
        hal_ranges = ','.join(rng(s, COL_HAL) for s in sheets)
        totals.write_formula(row, 2, f"=AVERAGE({acc_ranges})", num_fmt)
        totals.write_formula(row, 3, f"=AVERAGE({flu_ranges})", num_fmt)
        totals.write_formula(row, 4, f"=AVERAGE({ped_ranges})", num_fmt)
        totals.write_formula(row, 5, f"=AVERAGE({dis_ranges})", num_fmt)
        totals.write_formula(row, 6, f"=AVERAGE({hal_ranges})", num_fmt)

    totals.freeze_panes(1, 0)
    totals.autofilter(0, 0, len(groups), len(totals_headers)-1)
    for c in range(len(totals_headers)):
        totals.set_column(c, c, 24)
    totals.set_row(0, 20)

    wb.close()
    print(f"Wrote rater workbook to {output_xlsx}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='data/jfleg_eval_four_sets.csv')
    p.add_argument('--output', default='data/jfleg_eval_four_sets_rater.xlsx')
    args = p.parse_args()
    main(args.input, args.output)
