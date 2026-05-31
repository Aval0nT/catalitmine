# paper-fetcher-mcp 设计草案 v1

## 目标
为 CO2 hydrogenation 文献项目提供一个最小可用的浏览器自动化 MCP，复用学校登录态，按 DOI/标题检索论文，跳转全文页面，并下载 PDF 到固定目录。

## v1 范围
只解决最关键链路，不追求一步支持所有网站。

### v1 支持优先级
1. Scopus（检索入口）
2. WorldCat / Fulltext@UBU（馆藏解析/跳转）
3. ScienceDirect（首个目标出版社）

后续再补：ACS、Wiley、Springer、Google Scholar。

## 项目目录建议
放在 `/Users/avalont/Projects/knowledge/Science/` 下：

- `paper-fetcher-mcp/` — MCP 服务代码
- `browser-profile/` — 持久化浏览器 profile
- `pdfs/` — PDF 下载目录
- `data/` — DOI 列表、下载结果日志
- `notes/` — 设计稿与运行说明

## 关键设计原则

### 1. 登录态不绕过，只复用
- 你手动完成 Utrecht / WorldCat / Scopus 登录。
- MCP 始终复用同一个浏览器 profile。
- 登录过期时提示人工重新登录，不尝试规避 SSO/2FA。

### 2. 先做单篇成功，再做批量
- 先拿 `10.1016/j.apcatb.2021.120073` 打通链路。
- 单篇稳定后再做 DOI 列表批处理。

### 3. 先支持“能定位和下载”，再做花哨功能
- 先不做复杂推荐系统。
- 先保证搜索、跳转、保存和结果回报可靠。

## 技术方案
- Node.js + TypeScript
- Playwright
- 持久化浏览器上下文（persistent context）
- MCP server（stdio）

## 环境参数
建议默认值：

- `SCIENCE_ROOT=/Users/avalont/Projects/knowledge/Science`
- `BROWSER_PROFILE_DIR=/Users/avalont/Projects/knowledge/Science/browser-profile`
- `PDF_DOWNLOAD_DIR=/Users/avalont/Projects/knowledge/Science/pdfs`
- `HEADLESS=false`（v1 调试阶段）

## MCP 工具设计（v1）

### 1. `launch_browser`
启动持久化 profile 浏览器。

输入：
- `headless?: boolean`

返回：
- `ok`
- `profileDir`
- `currentUrl`
- `openPages`

### 2. `open_portal`
打开指定入口。

输入：
- `portal`: `scopus` | `worldcat` | `sciencedirect`

返回：
- `ok`
- `url`
- `title`
- `loginSignals[]`

### 3. `search_paper`
在指定入口按 DOI 或标题搜索。

输入：
- `source`: `scopus` | `worldcat`
- `query`: string
- `queryType`: `doi` | `title`

返回：
- `ok`
- `source`
- `query`
- `results[]`:
  - `title`
  - `url`
  - `snippet?`
  - `hasFulltextSignals?`

### 4. `open_result`
打开搜索结果中的某一项。

输入：
- `resultIndex`: number

返回：
- `ok`
- `url`
- `title`
- `fulltextSignals[]`

### 5. `open_fulltext`
尝试点击全文相关按钮。

优先识别文案：
- `View at Publisher`
- `Full Text`
- `Fulltext@UBU`
- `Access Online`
- `View Full Text`
- `Check for full text`

输入：
- `preferredText?: string`

返回：
- `ok`
- `fromUrl`
- `toUrl`
- `domain`
- `reachedPublisherPage`

### 6. `download_pdf`
在当前出版社页寻找 PDF 按钮并下载。

优先识别：
- `PDF`
- `Download PDF`
- `View PDF`

输入：
- `filename?: string`
- `downloadDir?: string`

返回：
- `ok`
- `savedPath?`
- `fileSizeBytes?`
- `finalUrl`
- `notes[]`

### 7. `get_session_status`
检查当前 profile 是否可用，是否疑似仍保持登录。

输入：
- `portal`: `scopus` | `worldcat`

返回：
- `ok`
- `portal`
- `url`
- `title`
- `loggedInLikely`
- `signals[]`

## 首个验证流程
目标 DOI：`10.1016/j.apcatb.2021.120073`

预期步骤：
1. `launch_browser`
2. 你手动登录学校链路（如有必要）
3. `open_portal(scopus)`
4. `search_paper(source=scopus, query=DOI)`
5. `open_result(0)`
6. `open_fulltext()`
7. 如果落到 ScienceDirect，则 `download_pdf()`

## 文件命名建议
v1 先采用最稳妥的 DOI 命名：

`10.1016_j.apcatb.2021.120073.pdf`

后续如果要更可读，再扩展为：

`2021__Applied_Catalysis_B__10.1016_j.apcatb.2021.120073.pdf`

## 失败处理
- 找不到结果：返回空结果，不报假成功
- 找不到全文按钮：返回当前页面 title/url 与已检测到的按钮文本
- 下载失败：记录页面 URL、尝试过的按钮和错误信息
- 登录失效：明确提示需要人工重新登录

## 你需要参与的环节
1. 首次登录 Utrecht / WorldCat / Scopus
2. 登录失效后的续期
3. 某些站点弹出的 2FA / SSO / captcha

## 我下一步要做的事
1. 建立 `paper-fetcher-mcp/` 代码骨架
2. 写 package.json / tsconfig / src 目录
3. 先实现一个“持久化 Playwright 启动器”
4. 再实现基础 portal 打开与搜索函数
5. 最后接 MCP 工具封装
