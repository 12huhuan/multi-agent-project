"""图表 API — 通过 AntV mcp-server-chart 生成可视化图表"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/charts", tags=["charts"])


@router.post("/bar")
async def generate_bar_chart(request: dict = {}):
    """生成柱状图"""
    title = request.get("title", "Chart")
    data = request.get("data", {"A": 10, "B": 20, "C": 15})

    try:
        from backend.app.agents.shared.chart_renderer import get_renderer
        renderer = await get_renderer()
        url = await renderer.bar_chart(title=title, data=data)
        return {"success": url is not None, "image_url": url, "type": "bar"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/pie")
async def generate_pie_chart(request: dict = {}):
    """生成饼图"""
    title = request.get("title", "Distribution")
    data = request.get("data", {"A": 30, "B": 45, "C": 25})

    try:
        from backend.app.agents.shared.chart_renderer import get_renderer
        renderer = await get_renderer()
        url = await renderer.pie_chart(title=title, data=data)
        return {"success": url is not None, "image_url": url, "type": "pie"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/radar")
async def generate_radar_chart(request: dict = {}):
    """生成雷达图 — 适合选品多维评分"""
    title = request.get("title", "Product Score")
    data = request.get("data", {"Product A": [8, 7, 6, 9], "Product B": [6, 8, 7, 5]})

    try:
        from backend.app.agents.shared.chart_renderer import get_renderer
        renderer = await get_renderer()
        url = await renderer.radar_chart(title=title, data=data)
        return {"success": url is not None, "image_url": url, "type": "radar"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/line")
async def generate_line_chart(request: dict = {}):
    """生成折线图 — 适合趋势展示"""
    title = request.get("title", "Trend")
    data = request.get("data", {"Sales": [100, 150, 200, 180, 220]})

    try:
        from backend.app.agents.shared.chart_renderer import get_renderer
        renderer = await get_renderer()
        url = await renderer.line_chart(title=title, data=data)
        return {"success": url is not None, "image_url": url, "type": "line"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/wordcloud")
async def generate_wordcloud(request: dict = {}):
    """生成词云图 — 适合关键词权重展示"""
    title = request.get("title", "Keywords")
    data = request.get("data", {"wireless": 100, "bluetooth": 85, "noise cancelling": 70})

    try:
        from backend.app.agents.shared.chart_renderer import get_renderer
        renderer = await get_renderer()
        url = await renderer.word_cloud(title=title, data=data)
        return {"success": url is not None, "image_url": url, "type": "wordcloud"}
    except Exception as e:
        return {"success": False, "error": str(e)}
