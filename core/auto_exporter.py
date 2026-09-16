"""Excel report for the desktop application, including embedded layout images."""
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Border, Font, PatternFill
from .exporter import _title, _header, _finish, THIN
from .optimizer import group_sheet_plans, validate_layout

COLORS = ["#b9ddf3", "#bee5cb", "#ffe09d", "#d9cdf4", "#fac7b5", "#aadedd"]


def diagram(plan, colors):
    image = Image.new("RGB", (1200, 900), "white")
    d = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/meiryo.ttc")
    if not font_path.exists():
        raise ValueError("図解用の日本語フォント（メイリオ）が見つかりません。")
    font = ImageFont.truetype(str(font_path), 24)
    small = ImageFont.truetype(str(font_path), 18)
    s = plan.sheet_type
    scale = min(930/s.width, 640/s.length)
    x, y = 190, 100
    w, h = s.width*scale, s.length*scale
    d.text((x, 15), f"大板幅 {s.width:g} mm", fill="#164e63", font=font)
    d.line((x, 70, x+w, 70), fill="#334155", width=2)
    for xx in (x, x+w):
        d.line((xx, 60, xx, 80), fill="#334155", width=2)
    d.text((5, y+h/2-35), f"大板長さ\n{s.length:g} mm", fill="#164e63", font=font)
    d.rectangle((x,y,x+w,y+h), fill="#64748b", outline="#334155", width=3)
    e = s.edge_loss*scale
    le=s.length_loss*scale
    d.rectangle((x+e,y+le,x+w,y+h-le), fill="#e5e7eb")
    for p in plan.placements:
        bounds=(x+p.x*scale,y+p.y*scale,x+(p.x+p.width)*scale,y+(p.y+p.length)*scale)
        d.rectangle(bounds, fill=colors[p.product_id], outline="#334155", width=2)
        label=f"{p.product_id}\n{p.width:g}×{p.length:g}" + ("\n90°回転" if p.rotated else "")
        box=d.multiline_textbbox((0,0),label,font=small)
        if box[2]+8 < bounds[2]-bounds[0] and box[3]+8 < bounds[3]-bounds[1]:
            d.multiline_text(((bounds[0]+bounds[2]-box[2])/2,(bounds[1]+bounds[3]-box[3])/2),label,fill="#142b40",font=small,align="center")
        elif bounds[2]-bounds[0]>30 and bounds[3]-bounds[1]>25:
            d.text((bounds[0]+3,bounds[1]+3),p.product_id,fill="#142b40",font=small)
    d.text((30, 790), f"濃い灰色＝幅ロス（片側 {s.edge_loss:g} mm）／薄い灰色＝端材・切断代",fill="#334155",font=font)
    d.text((30, 835), f"色付き＝製品（下表のIDと対応）／製品間切断代 {s.cut_allowance:g} mm",fill="#334155",font=font)
    stream=BytesIO()
    image.save(stream,format="PNG")
    stream.seek(0)
    return stream


def export_auto(destination, result, products, settings, candidate_no=1):
    errors=validate_layout(result)
    if errors:
        raise ValueError("配置に問題があります："+" / ".join(errors[:3]))
    path=Path(destination)
    path.parent.mkdir(parents=True,exist_ok=True)
    wb=Workbook()
    ws=wb.active
    ws.title="結果一覧"
    _title(ws,"大板長さ自動計算 — 取り合わせ結果",10)
    ws.append(["出力日時",datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"候補",candidate_no])
    ws.append(["状態","全数充足" if result.complete else "不足あり","大板枚数",len(result.sheets),"歩留り",result.yield_rate/100,"歩損",result.loss_rate/100])
    ws["F3"].number_format=ws["H3"].number_format="0.00%"
    ws.append(["大板幅(mm)",settings[0],"幅ロス(mm)",settings[1],"最大長さ(mm)",settings[2],"切断代(mm)",settings[3],"前後各ロス(mm)",settings[4] if len(settings)>4 else 0])
    ws.append(["注記","時間制限・中止時点の暫定候補" if result.timed_out else "探索候補（最適性の保証なし）"])
    ws.append(["説明","計算時点の結果です。入力欄を変更した場合はアプリで再計算してください。"])
    ws.append([])
    ws.append(["規格","板厚(mm)","大板幅(mm)","自動長さ(mm)","必要大板枚数"])
    _header(ws[8])
    counts=Counter((s.sheet_type.spec,s.sheet_type.thickness,s.sheet_type.width,s.sheet_type.length) for s in result.sheets)
    for (spec,t,w,h),n in counts.items():
        ws.append([spec or "未指定",t if t is not None else "未指定",w,h,n])
    ws.append([])
    ws.append(["製品ID","製品名","規格","板厚(mm)","幅(mm)","長さ(mm)","必要枚数","配置枚数","不足枚数","回転許可"])
    _header(ws[ws.max_row])
    for p in products:
        ws.append([p.id,p.name,p.spec or "未指定",p.thickness,p.width,p.length,p.required_qty,result.placed_by_product.get(p.id,0),result.shortage_by_product[p.id],"可" if p.rotation_allowed else "不可"])
    ws.append([])
    ws.append(["計算式","有効幅＝大板幅－幅ロス。大板長さ＝配置の最下端＋後端ロス（前端ロスは配置座標に含む）。"])
    ws.append(["歩留り","製品総面積 ÷ 投入大板総面積 × 100。歩損＝100－歩留り。"])
    colors={p.id:COLORS[i%len(COLORS)] for i,p in enumerate(products)}
    product_map={p.id:p for p in products}
    _finish(ws,[15,26,19,19,19,19,18,18,16,16])
    for sheet in wb:
        for row in sheet:
            for cell in row:
                if cell.row>1 and cell.fill.fgColor.rgb!="001F4E78":
                    cell.font=Font(name="Yu Gothic",size=11)
                cell.alignment=Alignment(vertical="center",wrap_text=True)
                if cell.value is not None:
                    cell.border=Border(bottom=THIN)
                if isinstance(cell.value,str) and cell.value.startswith("="):
                    cell.data_type="s"
        if sheet.title=="結果一覧":
            for r in (5,6,sheet.max_row-1,sheet.max_row):
                sheet.merge_cells(start_row=r,start_column=2,end_row=r,end_column=10)
        else:
            for r in range(sheet.max_row-2,sheet.max_row+1):
                sheet.merge_cells(start_row=r,start_column=2,end_row=r,end_column=8)
        for row in sheet:
            if row[0].row<5 or sheet.title=="結果一覧" or row[0].row>=40:
                sheet.row_dimensions[row[0].row].height=34
    from .layout_overview import overview
    from openpyxl.worksheet.page import PageMargins
    layout=wb.create_sheet("図解一覧")
    picture=ExcelImage(overview(result,colors,diagram))
    picture.width,picture.height=1200,800
    layout.add_image(picture,"A1")
    for col in "ABCDEFGHIJKL":
        layout.column_dimensions[col].width=14
    for row in range(1,41):
        layout.row_dimensions[row].height=15
    layout.sheet_view.showGridLines=False
    layout.page_setup.orientation="landscape"
    layout.page_setup.paperSize=layout.PAPERSIZE_A4
    layout.page_setup.fitToWidth=1
    layout.page_setup.fitToHeight=1
    layout.sheet_properties.pageSetUpPr.fitToPage=True
    layout.page_margins=PageMargins(left=0.2,right=0.2,top=0.2,bottom=0.2,header=0,footer=0)
    layout.print_area="A1:L40"
    layout.print_options.horizontalCentered=True
    wb.save(path)
    return path
