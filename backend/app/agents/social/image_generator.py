"""
图片生成 Agent — 调用 image-gen MCP (Replicate Flux) 生成社媒配图。

为每个帖子生成对应的社交媒体图片，支持多种风格和尺寸。
"""

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

IMAGE_SIZES = {
    "instagram_post": "1080x1080",
    "instagram_story": "1080x1920",
    "pinterest": "1000x1500",
    "facebook": "1200x630",
    "generic_square": "1024x1024",
}


class ImageGeneratorInput(BaseModel):
    prompt: str = Field(..., min_length=1, description="图片生成提示词")
    style: str = "product photography"
    platform: str = "instagram"
    image_size: str = "instagram_post"
    negative_prompt: str = "text, watermark, logo, low quality, blurry"
    num_images: int = Field(default=1, ge=1, le=4)


class GeneratedImage(BaseModel):
    url: str = ""
    prompt_used: str = ""
    style: str = ""
    size: str = ""


class ImageGeneratorOutput(BaseModel):
    images: list[GeneratedImage] = Field(default_factory=list)
    style_used: str = ""
    platform: str = ""


class ImageGeneratorAgent(BaseAgent[ImageGeneratorInput, ImageGeneratorOutput]):
    name = "image_generator"
    description = "调用 Replicate Flux MCP 生成社媒配图"

    def build_prompt(self, input_data: ImageGeneratorInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""  # 不直接用 LLM，委托给 MCP

    async def run(self, input_data: ImageGeneratorInput, context: dict | None = None) -> ImageGeneratorOutput:
        import time
        start = time.time()

        size = IMAGE_SIZES.get(input_data.image_size, "1024x1024")
        images = []

        # 尝试调用 image-gen MCP
        mcp_result = await self._try_mcp_generate(input_data, size)
        if mcp_result:
            images = mcp_result
        else:
            # 回退：返回占位信息，标记为模拟
            images = [
                GeneratedImage(
                    url=f"[image-gen] {input_data.prompt[:100]}...",
                    prompt_used=input_data.prompt,
                    style=input_data.style,
                    size=size,
                )
                for _ in range(input_data.num_images)
            ]

        duration_ms = int((time.time() - start) * 1000)
        result = ImageGeneratorOutput(
            images=images,
            style_used=input_data.style,
            platform=input_data.platform,
        )

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result

    async def _try_mcp_generate(self, input_data: ImageGeneratorInput, size: str) -> list[GeneratedImage]:
        """尝试通过 image-gen MCP 生成图片"""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            server_params = StdioServerParameters(
                command="node",
                args=["C:\\Users\\huhuan\\Desktop\\Image-Generation-MCP-Server\\build\\index.js"],
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    full_prompt = (
                        f"{input_data.prompt}, {input_data.style}, "
                        f"e-commerce product photo, professional lighting, clean background"
                    )
                    result = await session.call_tool("generate-image", {
                        "prompt": full_prompt,
                        "size": size,
                        "num_outputs": input_data.num_images,
                        "negative_prompt": input_data.negative_prompt,
                    })

                    if result and result.content:
                        # 解析 MCP 返回的图片 URL
                        import json
                        data = json.loads(result.content[0].text) if isinstance(result.content[0].text, str) else {}
                        urls = data.get("urls", data.get("images", []))
                        if isinstance(urls, str):
                            urls = [urls]
                        return [
                            GeneratedImage(url=u, prompt_used=input_data.prompt, style=input_data.style, size=size)
                            for u in urls[:input_data.num_images]
                        ]
        except Exception:
            pass
        return []
