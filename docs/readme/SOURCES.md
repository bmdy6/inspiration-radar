# README 图像来源

hero 使用本项目实际 CLI 的离线 demo 输出，输入是包内 `inspiration_radar/demo.json`。候选和评分是明确虚构的 fixture，没有调用模型，没有使用真实个人资料。输出保存 Markdown 与 JSON，图中路径相对于运行目录。

`art.json`、`art-manifest.json` 与 `captures/demo-final.json` 保存复现配置、图像哈希和原始运行回执。渲染器为 readme-from-code 的 hero-terminal 模板。英文图片仍包含示例条目里的中文内容，因为它们直接来自同一次 stdout。

实际评分公式是五维分数与配置权重的加权和；此图只展示日报产生和文件路径，不展示评分正确性或线上投递。
