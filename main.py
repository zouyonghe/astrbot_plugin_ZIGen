import asyncio
import base64
import os
from typing import Any

import aiohttp

from astrbot.api.all import *


TEMP_PATH = os.path.abspath("data/temp")


@register("ZIGen", "buding(AstrBot)", "调用自定义生成接口返回图片", "1.0.2")
class ZIGenerator(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self.task_semaphore = asyncio.Semaphore(config.get("max_concurrent_tasks", 5))
        os.makedirs(TEMP_PATH, exist_ok=True)

    async def terminate(self):
        """插件卸载时关闭 HTTP 会话"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def ensure_session(self):
        """确保 HTTP 会话存在"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(self.config.get("timeout", 120))
            self.session = aiohttp.ClientSession(timeout=timeout)

    @staticmethod
    def _strip_data_prefix(image_str: str) -> str:
        """移除 data:image/...;base64, 前缀"""
        if image_str.startswith("data:image"):
            _, _, data = image_str.partition(",")
            return data
        return image_str

    def _trans_prompt(self, prompt: str) -> str:
        """直接返回提示词"""
        return prompt

    @staticmethod
    def _extract_prompt_from_message(event: AstrMessageEvent) -> str:
        """从原始消息文本还原带空格的提示词"""
        full = (event.message_str or "").strip()
        if not full:
            return ""

        # 去掉命令前缀与子命令
        tokens = full.split()
        if tokens and tokens[0].lstrip("/") in ("zi",):
            tokens = tokens[1:]
        if tokens and tokens[0] == "gen":
            tokens = tokens[1:]

        return " ".join(tokens).strip()

    def _build_payload(self, prompt: str) -> dict[str, Any]:
        """构造发送到 ZIGen 接口的 payload"""
        params = self.config["default_params"]
        payload = {
            "prompt": self._trans_prompt(prompt).strip(),
            "negative_prompt": params.get("negative_prompt", "").strip(),
            "steps": params.get("steps", 9),
            "guidance": params.get("guidance", 0),
            "height": params.get("height", 512),
            "width": params.get("width", 512),
        }

        seed = params.get("seed", -1)
        if isinstance(seed, int) and seed >= 0:
            payload["seed"] = seed

        if not payload["negative_prompt"]:
            payload.pop("negative_prompt")

        return payload

    def _normalize_image(self, image_item: Any) -> str:
        """兼容不同响应结构，统一返回 base64 编码"""
        if isinstance(image_item, dict):
            if "data" in image_item:
                image_item = image_item["data"]
            elif "image" in image_item:
                image_item = image_item["image"]
            elif "base64" in image_item:
                image_item = image_item["base64"]

        if not isinstance(image_item, str):
            raise ValueError("响应中未找到有效的图像数据")

        image_b64 = self._strip_data_prefix(image_item)
        if not image_b64:
            raise ValueError("图像数据为空")
        return image_b64

    async def _request_images(self, payload: dict[str, Any]) -> list[str]:
        """调用 ZIGen 服务并返回图片列表"""
        await self.ensure_session()
        url = self.config["service_url"]

        async with self.session.post(url, json=payload) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise ConnectionError(f"接口返回异常 {resp.status}: {error}")

            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                data = await resp.json()
                images_field = (
                    data.get("images")
                    or data.get("data")
                    or data.get("image")
                )
                if images_field is None:
                    raise ValueError("响应格式中缺少 images/image 字段")

                if isinstance(images_field, list):
                    raw_images = images_field
                else:
                    raw_images = [images_field]

                return [self._normalize_image(item) for item in raw_images]

            content = await resp.read()
            return [base64.b64encode(content).decode("utf-8")]

    def _render_conf(self) -> str:
        params = self.config.get("default_params", {})
        negative_prompt = params.get("negative_prompt", "").strip() or "未设置"
        seed = params.get("seed", -1)
        seed_text = seed if isinstance(seed, int) and seed >= 0 else "随机"

        return (
            f"- 服务地址: {self.config.get('service_url')}\n"
            f"- 尺寸: {params.get('width', 512)}x{params.get('height', 512)}\n"
            f"- 步数: {params.get('steps', 9)}\n"
            f"- Guidance: {params.get('guidance', 0)}\n"
            f"- 种子: {seed_text}\n"
            f"- 负面提示词: {negative_prompt}\n"
            f"- 详略模式: {'开启' if self.config.get('verbose', True) else '关闭'}"
        )

    @command_group("zi")
    def zi(self):
        pass

    @zi.command("gen")
    async def generate_image(self, event: AstrMessageEvent, prompt: str):
        """生成图片"""
        async with self.task_semaphore:
            try:
                prompt = self._extract_prompt_from_message(event)
                if not prompt:
                    yield event.plain_result("⚠️ 需要提供提示词")
                    return
                if self.config.get("verbose", True):
                    yield event.plain_result("🎨 正在调用 ZIGen 服务，请稍候...")

                images = await self._request_images(self._build_payload(prompt))
                chain = [Image.fromBase64(img) for img in images]
                yield event.chain_result(chain)

                if self.config.get("verbose", True):
                    yield event.plain_result("✅ 图像生成完成")

            except Exception as e:
                logger.error(f"ZIGen 生成失败: {e}")
                yield event.plain_result("❌ 生成失败，请检查服务地址、参数或日志")

    @zi.command("url")
    async def set_service_url(self, event: AstrMessageEvent, service_url: str):
        """设置服务地址"""
        if not service_url.startswith(("http://", "https://")):
            yield event.plain_result("⚠️ 地址需包含 http:// 或 https:// 前缀")
            return

        self.config["service_url"] = service_url
        self.config.save_config()
        yield event.plain_result(f"✅ 服务地址已更新为: {service_url}")

    @zi.command("size")
    async def set_size(self, event: AstrMessageEvent, width: int, height: int):
        """设置生成图片的尺寸"""
        if (
            not isinstance(width, int)
            or not isinstance(height, int)
            or width < 1
            or height < 1
            or width > 2048
            or height > 2048
        ):
            yield event.plain_result("⚠️ 宽高需在 1-2048 之间的整数")
            return

        self.config["default_params"]["width"] = width
        self.config["default_params"]["height"] = height
        self.config.save_config()
        yield event.plain_result(f"✅ 已设置生成尺寸为 {width}x{height}")

    @zi.command("step")
    async def set_steps(self, event: AstrMessageEvent, steps: int):
        """设置采样步数"""
        if steps < 1 or steps > 200:
            yield event.plain_result("⚠️ 步数需在 1-200 范围内")
            return

        self.config["default_params"]["steps"] = steps
        self.config.save_config()
        yield event.plain_result(f"✅ 步数已设置为: {steps}")

    @zi.command("guidance")
    async def set_guidance(self, event: AstrMessageEvent, guidance: float):
        """设置 guidance 数值"""
        if guidance < 0 or guidance > 50:
            yield event.plain_result("⚠️ guidance 需在 0-50 范围内")
            return

        self.config["default_params"]["guidance"] = guidance
        self.config.save_config()
        yield event.plain_result(f"✅ guidance 已设置为: {guidance}")

    @zi.command("seed")
    async def set_seed(self, event: AstrMessageEvent, seed: int):
        """设置随机种子，-1 表示随机"""
        if seed < -1:
            yield event.plain_result("⚠️ 种子应大于等于 -1")
            return

        self.config["default_params"]["seed"] = seed
        self.config.save_config()
        seed_text = "随机" if seed < 0 else seed
        yield event.plain_result(f"✅ 种子已设置为: {seed_text}")

    @zi.command("conf")
    async def show_conf(self, event: AstrMessageEvent):
        """查看当前配置"""
        yield event.plain_result(f"⚙️ 当前配置:\n{self._render_conf()}")

    @zi.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示使用说明"""
        help_msg = [
            "🖼️ ZIGen 插件使用指南",
            "- `/zi gen [提示词]`：按照默认参数生成图片。",
            "- `/zi url [地址]`：设置生成服务地址（例如 http://127.0.0.1:9000/generate）。",
            "- `/zi size [宽] [高]`：设置默认生成尺寸。",
            "- `/zi step [步数]`：设置默认步数。",
            "- `/zi guidance [数值]`：设置 guidance 数值。",
            "- `/zi seed [种子]`：设置固定种子，-1 表示随机。",
            "- `/zi conf`：查看当前配置。",
            "- `/zi help`：显示本帮助信息。",
            "提示：如命令参数中无法直接输入空格，可用 `~` 代替，插件会自动还原为空格。",
        ]
        yield event.plain_result("\n".join(help_msg))

    @llm_tool("zigen_generate_image")
    async def generate_image_tool(self, event: AstrMessageEvent, prompt: str):
        """Generate images using Z-Image based on the given prompt.
        Call only when the user intent is to generate/draw/create an image, not for searching.

        Args:
            prompt (string): The prompt or description used for generating images.
        """
        async for result in self.generate_image(event, prompt):
            yield result
