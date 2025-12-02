# astrbot_plugin_ZIGen

## 介绍
轻量生图插件，向 Z-Image WebUI 的 `/generate` 接口发送请求并将返回的图片发送给用户。默认请求体与 zimage-webui 的示例 curl 一致，可配置服务地址、分辨率、步数、guidance、随机种子和负面提示词。

### Z-Image WebUI（参考 /home/buding/Code/zimage-webui）
- 本地权重的轻量 Web UI，前端提供提示词/负面词、步数、引导强度、种子、分辨率预设（512/768/1024，16 像素步长限制）。
- 一次点击可连续生成 1–10 张，默认随机种子；填写固定种子则按该值生成。
- 每次生成自动写入 `outputs/`，文件名包含时间戳、分辨率和种子（无种子时标记 `rand`），接口返回的 `meta.saved_path` 也会给出保存路径。
- 默认监听 `0.0.0.0:9000`，浏览器打开 `http://localhost:9000` 即可。

## 快速开始
1) 运行 zimage-webui（参考 README）：
```bash
# 安装匹配 CUDA 的 torch/torchvision（示例 CUDA 12.1）
# pip install torch==2.5.1+cu121 torchvision==0.20.1 -f https://download.pytorch.org/whl/torch_stable.html

cd /home/buding/Code/zimage-webui
pip install -r requirements.txt
cd scripts && bash download_models.sh && cd ..
python webui_server.py  # 默认 0.0.0.0:9000，可用 ZIMAGE_PORT 修改
```

2) AstrBot 中安装本插件，配置 `service_url`（默认 `http://127.0.0.1:9000/generate`）。

3) 发送 `/zi gen a cat sitting on a chair~high quality~detailed` 试跑（命令无法直接输入空格时可用 `~` 代替，插件会自动还原为空格）。

## 配置说明（`_conf_schema.json`）
- `service_url`：生成服务完整地址，默认 `http://127.0.0.1:9000/generate`。
- `verbose`：开启后在生成阶段输出提示。
- `timeout`：请求超时时间（秒）。
- `max_concurrent_tasks`：最大并发生成数量。
- `default_params.width/height/steps/guidance/seed/negative_prompt`：对应请求体参数，`seed` 为 `-1` 时表示随机。
- `replace_space`：命令中若无法输入空格，可用此字符占位（默认 `~`），发送前会自动转回空格。

## 指令
- `/zi gen [提示词]`：使用当前默认参数生成图片。
- `/zi url [地址]`：修改生成服务地址。
- `/zi size [宽] [高]`：设置默认宽高（1-2048）。
- `/zi step [步数]`：设置默认步数（1-200）。
- `/zi guidance [数值]`：设置 guidance（0-50）。
- `/zi seed [种子]`：设置随机种子，`-1` 表示随机。
- `/zi conf`：查看当前配置。
- `/zi help`：查看帮助。

## 依赖
- aiohttp
