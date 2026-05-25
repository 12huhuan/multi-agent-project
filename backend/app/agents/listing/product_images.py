"""产品图片生成 Agent — 通过 Pollinations.ai 免费生成 Amazon Listing 配图"""

from urllib.parse import quote

from pydantic import BaseModel, Field
from backend.app.agents.base import BaseAgent

# Amazon Listing 常用图片尺寸
IMAGE_SIZES = {
    "main": (2000, 2000),
    "lifestyle": (1500, 1500),
    "detail": (1000, 1000),
    "aplus_banner": (970, 600),
    "aplus_square": (300, 300),
}


class ProductImageInput(BaseModel):
    product_name: str = Field(..., min_length=1)
    category: str = ""
    features: list[str] = Field(default_factory=list)
    image_descriptions: list[str] = Field(default_factory=list)
    style: str = "product photography, white background, e-commerce"


class ProductImage(BaseModel):
    url: str = ""
    description: str = ""
    prompt: str = ""
    size: str = ""


class ProductImageOutput(BaseModel):
    images: list[ProductImage] = Field(default_factory=list)


class ProductImageAgent(BaseAgent[ProductImageInput, ProductImageOutput]):
    name = "product_image_generator"
    description = "通过 Pollinations.ai 免费生成产品 Listing 图片"

    def build_prompt(self, input_data: ProductImageInput, context: dict | None = None) -> tuple[str, str]:
        return "", ""

    async def run(self, input_data: ProductImageInput, context: dict | None = None) -> ProductImageOutput:
        import time
        start = time.time()

        descriptions = input_data.image_descriptions if input_data.image_descriptions else [
            f"{input_data.product_name} main product shot, isolated on pure white background",
            f"{input_data.product_name} lifestyle image, in use, natural lighting",
            f"{input_data.product_name} detail close-up, premium materials texture",
        ]

        sizes = ["main", "lifestyle", "detail"]
        images = []

        for i, desc in enumerate(descriptions[:5]):
            w, h = IMAGE_SIZES.get(sizes[min(i, len(sizes) - 1)], (1500, 1500))
            size_key = sizes[min(i, len(sizes) - 1)]

            short_desc = desc[:100].rsplit(" ", 1)[0] if len(desc) > 100 else desc
            full_prompt = f"{short_desc}, {input_data.style}"
            encoded = quote(full_prompt, safe="")
            img_url = f"https://image.pollinations.ai/prompt/{encoded}?width={w}&height={h}&nologo=true"

            images.append(ProductImage(
                url=img_url,
                description=desc[:120],
                prompt=full_prompt[:200],
                size=f"{w}x{h}",
            ))

        duration_ms = int((time.time() - start) * 1000)
        result = ProductImageOutput(images=images)

        tid = context.get("task_id") if context else None
        if tid:
            await self.log_execution(tid, input_data, result, 0, duration_ms)

        return result
