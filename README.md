# 孔明 Kongming

> 运筹帷幄之中，决胜千里之外。

**孔明是一个“总入口”技能。** 你不用记住、也不用挑选装了哪些技能，只要说出需求——写 SEO 文章、改文案、找选题、做产品分析……孔明会：

1. **听懂需求**（隆中对）：理清最终交付、材料、约束，冻结验收标准；
2. **动态点将**：扫描本机已安装的全部技能，连同模型自身能力，按需选出最合适的一个或几个；
3. **交叉验证**（会审 / 舌战）：多个技能都能做同一件事时，让它们各自独立出稿，建立共识/分歧矩阵，对分歧做证据裁决和辩论；
4. **三审定稿**：校对（proofread）→ 核验（validate）→ 评审（review），各方都认可后才交付；
5. **白标交付**：默认不显示用了哪些技能、作者或品牌，所有成果都是孔明的成果；可随时开启出处显示；
6. **隐身操作**：连工具调用记录里也只有中性的代号（如 `s3fa91c`），看不到技能名、作者和路径；终端无痕模式只输出最终结果；
7. **自动更新**：每次调用前静默把用到的技能更新到最新，失败自动跳过，不打扰、不暴露；
8. **多语言匹配**：中、英、日、韩、西、法、德等语言的需求和技能描述可以互相匹配。

## 为什么叫孔明

- **军师**：诸葛亮（字孔明）是中国最家喻户晓的军师——不亲自上阵，却知人善任、调兵遣将，正是“技能调度”的角色。
- **三个臭皮匠，顶个诸葛亮**：孔明的会审机制就是让多个“臭皮匠”（技能）各出其策，再由孔明去伪存真，得出比任何一方都可靠的定策。
- **锦囊妙计**：配置就叫“锦囊”，交给孔明的事，打开锦囊就有办法。
- **草船借箭**：借众家之长为己所用，产出却只署孔明之名。

触发词：**孔明** / **kongming** / **军师** / `/kongming`，配置叫 **锦囊**。两个字、拼音好打，中英文都好记。

## 安装

```bash
git clone https://github.com/iamzifei/kongming.git
cd kongming
./install.sh          # 复制到 ~/.claude/skills/kongming
./install.sh --link   # 或者软链接，git pull 即更新
./install.sh --all    # 同时装到 ~/.agents/skills、~/.codex/skills（存在时）
./install.sh --bin    # 安装无痕命令 kongming 到 ~/.local/bin
./install.sh --focus  # 把 Claude Code 默认视图设为专注视图
```

需要 Python 3.9+（只用标准库；装了 PyYAML 会优先使用）。

## 使用

```
孔明，帮我写一篇关于“露营装备选购”的 SEO 文章，目标是百度和 Google 首页
孔明，下周小红书发什么？账号是做职场穿搭的
孔明，分析一下这个产品的商业模式：<链接>
/kongming 把这段文案改得更有转化力：……
```

## 完全隐藏工具调用记录

Claude Code 本身没有“彻底关闭工具记录”的开关，孔明分三层处理：

| 层级 | 做法 | 能看到什么 |
| --- | --- | --- |
| 默认 | 所有技能访问都经过 `km.py`，只用代号；输出已脱敏 | 工具记录里只有 `km.py load s3fa91c` 这类中性条目，看不到技能名、作者、路径 |
| 专注视图 | Claude Code 里输入 `/focus`，或 `./install.sh --focus` 设为默认 | 只显示你的提问、一行工具摘要和最终回复 |
| **无痕模式** | 终端运行 `kongming "需求"`（`./install.sh --bin` 安装） | **只有最终结果**，没有任何工具调用记录 |

```bash
kongming "帮我写一篇露营装备选购的 SEO 文章"
kongming -c "标题再短一点"            # 接着上一次继续
cat brief.md | kongming               # 从文件读需求
KONGMING_PERMISSION_MODE=auto kongming "……"   # 调整权限模式（默认 acceptEdits）
```

无痕模式底层是 `claude -p --output-format text`，预先放行了孔明自身脚本、读写文件、子 Agent 和联网搜索；需要其他权限时可通过 `KONGMING_PERMISSION_MODE` 调整。

## 自动更新

每次调用技能前，孔明会先把它更新到最新，**不征求同意**：

- **插件技能**：`claude plugin marketplace update` + `claude plugin update`
- **git 安装的技能**（包括软链接到 git 仓库的）：工作区干净时 `git pull --ff-only`；有本地改动则不碰
- **skills CLI 安装的技能**：`npx skills update`（尽力而为）
- **技能自带的版本检查**：照常执行，发现新版本就按技能自己的方式更新

断网、超时、更新失败都直接跳过，用现有版本继续；更新过程和结果不会出现在回复里，也不会显示是哪个技能。想减少更新频率：`kongming_config.py set update_interval_minutes 60`；关闭：`set auto_update false`。

## 多语言匹配

需求和技能描述用不同语言写也能对上，排序综合三层信号：

1. **字面**：Unicode 归一、英文词干化、中日韩文字切分；
2. **跨语言概念词表**（`scripts/lexicon.json`，60 个常用概念 × 7 种语言）：「选题 / topic ideas / ネタ / 주제 선정」都映射到同一概念；可在 `~/.kongming/lexicon.json` 追加自己的说法；
3. **技能画像**：孔明第一次遇到某个技能时，会为它写一份多语言关键词和双语摘要并缓存，之后检索直接复用；技能更新后自动重写。

每次检索时孔明还会把需求翻译成多语言关键词一起传入，最后对前 20 名做语义判断再决定用谁。

想让孔明成为默认入口（不用每次喊名字），可在 `~/.claude/CLAUDE.md` 里加一句：

```
处理写作、营销、选题、分析、调研、策划类任务时，默认使用 kongming 技能。
```

## 锦囊（设置）

直接在对话里说就行：

| 说法 | 效果 |
| --- | --- |
| 孔明，以后显示出处 | 文末列出实际使用的技能及作用（`brief`） |
| 孔明，给我看完整验证过程 | 再附交叉验证报告：共识/分歧、裁决依据、三审记录（`full`） |
| 孔明，别显示来源 | 恢复默认白标（`off`） |
| 孔明，这次显示一下用了什么 | 仅本次显示，不改设置 |
| 孔明，别用 xxx | 把某技能加入排除列表 |
| 孔明，锦囊 | 查看当前全部设置 |

或者用命令行：

```bash
python3 ~/.claude/skills/kongming/scripts/kongming_config.py show
python3 ~/.claude/skills/kongming/scripts/kongming_config.py set show_sources brief
python3 ~/.claude/skills/kongming/scripts/kongming_config.py set max_skills 2
```

全部配置项见 [skills/kongming/references/config.md](skills/kongming/references/config.md)。

## 工作原理

```
需求 ──▶ 隆中对（理解 + 冻结验收标准）
          │
          ▼
        点将（km.py scan：全部已装技能 → 多语言排序 → 倒推拆解 → 选阵型）
          │
        更新（静默，失败即跳过）→ 读取（代号 + 脱敏）
          │
   ┌──────┼───────────┬──────────────┐
  独断    单将         连环            会审
(模型本身)(一个技能)  (技能串联)   (多技能 + 模型本家 独立出稿)
   │      │           │              │
   │      │           │         舌战：共识矩阵 → 证据裁决 → 辩论
   │      │           │              │
   └──────┴─────┬─────┴──────────────┘
                ▼
          三审：校对 → 核验 → 评审（各方表态，阻塞则重修，最多 2 轮）
                ▼
          净稿：km.py check 白标检查（off 模式）
                ▼
          以孔明之名交付（按设置附出处）
```

动态路由借鉴了 [dbskill](https://github.com/dontbesilent2025/dbskill) 入口 `/dbs` 的做法：从最终交付倒推、按“接手什么 → 交出什么 → 不交出什么”衔接步骤、串行/并行/闸门/隔离对照等组合结构。不同之处在于孔明不限于某一套技能，而是面向本机安装的**所有**技能（项目、用户、插件目录），并把“多技能交叉验证 + 三审 + 白标”作为默认流程。

## 目录

```
skills/kongming/
├── SKILL.md                    # 主流程
├── references/
│   ├── routing.md              # 点将规则（动态路由）
│   ├── council.md              # 会审协议（交叉验证、辩论、三审）
│   ├── white-label.md          # 白标规则
│   └── config.md               # 锦囊（配置项）
└── scripts/
    ├── km.py                   # 统一入口：scan / profile / update / load / ls / exec / check / reveal
    ├── registry.py             # 技能发现、代号、输出脱敏
    ├── ranker.py               # 多语言排序（字面 + 概念 + 画像，BM25）
    ├── lexicon.json            # 跨语言概念词表
    ├── updater.py              # 静默更新
    ├── brand.py                # 提取技能名、作者、品牌等需隐藏的词
    ├── sanitize_check.py       # 白标检查规则
    ├── kongming_config.py      # 读写配置
    └── _common.py
bin/kongming                    # 无痕模式命令
tests/test_scripts.py           # python3 -m unittest discover tests
```

## 说明

- **隐身的边界。** 交互模式下展开工具详情（Ctrl+O）或打开子 Agent 记录（/tasks）仍能看到 `km.py` 中性条目和脱敏后的内容；孔明的本地缓存 `~/.kongming/registry.json` 里存有真实名称和路径（供出处模式使用）。要界面上完全不留痕迹，请用无痕模式。
- **脱敏是按词表做的。** 名字是通用词（如 `pdf`、`docx`）的技能不会被替换，因为这些词不指向任何作者或品牌；翻译过的名字、描述性暗示由孔明在通读时处理。
- **白标不等于说谎。** 未开启出处时，孔明会说“综合多种方法推演、核验的结果”，不会声称没用任何技能；开启后如实列出。
- **会审更慢、更耗 token。** 简单任务孔明会自动独断或单将；说“快一点”即可跳过会审。
- 如需再分发或商用他人的技能与产出，请遵守对应许可证（部分许可证要求保留署名）。
