# 马来西亚华文媒体接入核查

2026-11-26 MYT。依据 D-010 查找发布方公告或官网声明的 RSS/API，并核对 robots 与条款。以下证据来自公开政策及官网的订阅发现字段，未读取 RSS 条目或新闻文章正文。Actions 环境的连通性、响应结构和时效仍待阶段 B 的 `live-check`。

| 媒体 | 官方订阅证据和访问规则 | 本轮结论 |
| --- | --- | --- |
| 当今大马中文版 | 中文官网明确声明新闻 RSS `https://www.malaysiakini.com/zh/rss/news.rss`。同一主机 `robots.txt` 返回 200，通用组允许该路径并指定 1 秒间隔。英语和中文服务条款均保留编辑内容复制及在线使用的权利。 [中文官网](https://www.malaysiakini.com/zh) · [robots.txt](https://www.malaysiakini.com/robots.txt) · [中文条款](https://m8.malaysiakini.com/zh/terms/) · [英文条款](https://www.malaysiakini.com/en/about/terms-of-service) | 接入 D-010 已批准发布方的中文新闻订阅，供 Owner 私用。保留标题、规范链接、时间及媒体名等元数据。RSS 开放不扩张发布方权利。两语版在趋势评分中只计一家媒体，新闻栏目可展示语言不同的条目。 |
| 星洲日报 | 未核实官方公开 RSS 或 API；官网和 robots 核查均得到 403。集团公布的隐私政策并未许可归档新闻。 [官网](https://www.sinchew.com.my/) · [robots.txt](https://www.sinchew.com.my/robots.txt) · [集团隐私政策](https://guangming.com.my/privacy) | 不接入。 |
| 中国报 | 未核实由官网声明的 RSS 或 API。官网和 robots 核查均得到 403，未核实适用的订阅条款。 [官网](https://www.chinapress.com.my/) · [robots.txt](https://www.chinapress.com.my/robots.txt) · [集团官方资料](https://www.mediachinesegroup.com/wp-content/uploads/2024/05/e_00685_final-results-announcement_20240528.pdf) | 不接入。 |
| 东方日报 | 官网可读，未发现 RSS 自发现或发布方提供的订阅说明。robots 通用组禁止预览、最新电子报及 App 等路径，因无订阅 URL 无法核验具体 RSS 路径。使用条款保留复制及使用内容的权利。 [官网](https://www.orientaldaily.com.my/) · [robots.txt](https://www.orientaldaily.com.my/robots.txt) · [使用条款](https://www.orientaldaily.com.my/terms) | 不接入。 |
| 光华日报 | 未核实由新闻官网声明的 RSS 或 API。官网和 robots 核查均得到 403，电子报的订阅规则未提供新闻 RSS 使用依据。 [官网](https://www.kwongwah.com.my/) · [robots.txt](https://www.kwongwah.com.my/robots.txt) · [电子报](https://epaper.kwongwah.com.my/) | 不接入。 |
| 诗华日报 | 官网声明 `/feed/`，robots 通用组允许该路径。服务条款第 2、7 节保留复制和转载权，仅明确允许个人浏览阅读。本次没有找到 RSS 元数据归档的额外条件。 [官网](https://news.seehua.com/) · [robots.txt](https://news.seehua.com/robots.txt) · [服务条款](https://news.seehua.com/terms-of-service/) | 权限待核实。 |
| 南洋商报、光明日报 | 未核实可投入运行的官方 RSS/API。南洋商报官网和 robots 核查均得到 403；光明日报 robots 可读，官网检查得到 403，未获取可对照的官方订阅 URL。 [南洋商报官网](https://www.enanyang.my/) · [南洋商报 robots.txt](https://www.enanyang.my/robots.txt) · [光明日报 robots.txt](https://guangming.com.my/robots.txt) · [集团隐私政策](https://guangming.com.my/privacy) | 不接入。 |

403 表示当次合规核查无法读到响应，相关来源不进入白名单。现有 `www.malaysiakini.com` 白名单继续适用，精确端点只增加官方中文新闻 RSS。中文栏目与读者来函订阅、未声明路径和第三方网页转换源不纳入采集。
