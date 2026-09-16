from collections import Counter
from io import BytesIO
import math
from PIL import Image, ImageDraw, ImageFont


def overview(result, colors, render_diagram):
    from .optimizer import group_sheet_plans
    groups=group_sheet_plans(result.sheets)
    image=Image.new("RGB",(2400,1600),"white")
    draw=ImageDraw.Draw(image)
    font_path="C:/Windows/Fonts/meiryo.ttc"
    font=ImageFont.truetype(font_path,32)
    draw.text((40,20),f"取り合わせ図一覧  |  大板 {len(result.sheets)} 枚  |  {len(groups)} パターン  |  歩留り {result.yield_rate:.2f}%",font=font,fill="#173655")
    state="全数充足" if result.complete else "不足あり"
    draw.text((40,70),f"{state} / 各図は大板1枚分。×枚数が必要大板枚数。寸法単位：mm。製品IDの詳細は結果一覧を参照。",font=ImageFont.truetype(font_path,23),fill="#475569")
    n=max(1,len(groups))
    cols=max(1,math.ceil(math.sqrt(n*1.45)))
    if n==1: cols=1
    rows=math.ceil(n/cols)
    cw,ch=2320/cols,1370/rows
    for i,(plan,count,_) in enumerate(groups):
        x=int(40+(i%cols)*cw); y=int(120+(i//cols)*ch)
        w=int(cw-16); h=int(ch-16)
        draw.rectangle((x,y,x+w,y+h),outline="#B8C9DC",width=2)
        size=max(10,min(28,int(w/22),int(h/10)))
        heading=ImageFont.truetype(font_path,size)
        s=plan.sheet_type
        draw.text((x+8,y+6),f"Ptn {i+1}   {s.width:g}×{s.length:g} mm   ×{count}枚",font=heading,fill="#173655")
        counts=Counter(p.product_id for p in plan.placements)
        caption=" / ".join(f"{pid}:{qty}枚" for pid,qty in counts.items())
        # Wrap quantity labels without dropping products.
        lines=[]; line=""
        for char in caption:
            if draw.textlength(line+char,font=heading)>w-16 and line:
                lines.append(line); line=""
            line+=char
        if line: lines.append(line)
        foot=(size+5)*len(lines)+8
        source=Image.open(render_diagram(plan,colors)).crop((0,0,1200,760))
        source.thumbnail((max(1,w-16),max(1,h-size-24-foot)),Image.Resampling.LANCZOS)
        image.paste(source,(x+(w-source.width)//2,y+size+18))
        for j,line in enumerate(lines):
            draw.text((x+8,y+h-foot+j*(size+5)),line,font=heading,fill="#334155")
    losses=result.sheets[0].sheet_type if result.sheets else None
    note=f"幅ロス：片側{losses.edge_loss:g}mm / 長さロス：前後各{losses.length_loss:g}mm" if losses else ""
    draw.text((40,1520),"色＝製品 / 濃灰＝外周ロス / 薄灰＝端材・切断代 / "+note,font=ImageFont.truetype(font_path,24),fill="#475569")
    draw.text((40,1560),"パターン数が多い場合は図が小さくなります。製品寸法・必要数量は「結果一覧」で確認してください。",font=ImageFont.truetype(font_path,21),fill="#475569")
    stream=BytesIO()
    image.save(stream,format="PNG")
    stream.seek(0)
    return stream
