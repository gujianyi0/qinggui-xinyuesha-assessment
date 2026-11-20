# 知识书架本地导出

base保存既有知识书架的7方向、49目标/49原文快照，来源为同工作区知识浏览网页；第49篇《从使用者角度验证交互》于2026-11-17补齐。不是新增游戏资料，也不进入RAG。

本工具使用marked和sanitize-html导出正文与证据链接。知识文档仅为7方向49篇；12份文档导航QA（含项目README）单列为assessment_reference，不属于学习资料。原生阅读由轻归features/bookshelf和已有react-markdown/remark-gfm适配提供，发布副本不再包含原独立网页脚本、品牌或掌握进度。依赖精确版本及锁文件随仓库提供。第三方许可证见base/licenses；highlight.js仅对应历史静态高亮与样式。

更新项目文档后，从项目根目录执行：

```powershell
npm --prefix tools/bookshelf ci --ignore-scripts
npm --prefix tools/bookshelf run build
.\.venv\Scripts\python.exe -m scripts.verify_bookshelf
npm --prefix frontend run build:local
```

导出只覆盖本项目frontend/public/bookshelf下的生成副本，禁止将私人文件放入该生成目录。私有目录、真实.env和数据库不导出；仅精选文档链接可达的资料复制进入检阅副本。历史重构后不存在的三个旧路径显示为不可用，不伪造文件。

普通使用者直接使用已提交的静态副本即可，不需要安装本工具依赖。副本不调用Cloudflare、不连接D1、不含主人管理口令，也不修改云端掌握进度。公网知识书架若需发布更新，应单独执行其发布流程。

导出时移除考核目标及文章开头对应的目标提示，正文和引用保留。目录data.json仅载入标题、目录和证据映射；搜索时才按需载入search.json中的正文索引。静态副本不直接访问D1，轻归业务后端代理共享进度；公开访客只读。
