"""
图片生成 Agent — 通过 Pollinations.ai (免费) 生成社媒配图。

Pollinations.ai: 完全免费，无需注册/API Key，URL 即图片。
回退: 占位 URL
"""

from urllib.parse import quote

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

IMAGE_SIZES = {
    "instagram_post": (1080, 1080),
    "instagram_story": (1080, 1920),
    "pinterest": (1000, 1500),
    "facebook": (1200, 630),
    "generic_square": (1024, 1024),
}


class ImageGeneratorInput(BaseModel):
    prompt: str = Field(..., min_length=1)
    style: str = "product photography"
    platform: str = "instagram"
    image_size: str = "instagram_post"
    negative_prompt: str = ""
    num_images: int = Field(default=1, ge=1, le=1)


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
    description = "通过 Pollinations.ai 免费生成社媒配图"

    def build_prompt(self, input_data: ImageGeneratorInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""

    async def run(self, input_data: ImageGeneratorInput, context: dict | None = None) -> ImageGeneratorOutput:
        import time
        start = time.time()

        w, h = IMAGE_SIZES.get(input_data.image_size, (1024, 1024))
        size_str = f"{w}x{h}"

        # 截取 prompt 前 100 个字符，保持简洁
        short_prompt = input_data.prompt[:100].rsplit(" ", 1)[0] if len(input_data.prompt) > 100 else input_data.prompt
        full_prompt = f"{short_prompt}, {input_data.style}, professional lighting, clean background"
        encoded = quote(full_prompt, safe="")
        image_url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true"

        images = [
            GeneratedImage(
                url=image_url,
                prompt_used=input_data.prompt,
                style=input_data.style,
                size=size_str,
            )
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

