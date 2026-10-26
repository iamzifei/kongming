# 锦囊（配置）

配置文件：全局 `~/.kongming/config.json`，项目级 `<项目>/.kongming/config.json`（覆盖全局）。也可用环境变量 `KONGMING_CONFIG` 指定路径。

修改：`python3 <KM>/scripts/kongming_config.py set <项> <值>`（加 `--project` 写项目级）。用户在对话里直接说也可以，孔明会代为修改。

| 项 | 默认 | 说明 |
| --- | --- | --- |
| `show_sources` | `off` | `off` 不显示任何出处；`brief` 文末列出实际使用的技能及作用；`full` 再附交叉验证报告（阵型、共识/分歧、裁决依据、三审记录） |
| `mode` | `auto` | `auto` 自动选阵型；`single` 总是只用最对口的一个；`council` 能会审时尽量会审 |
| `max_skills` | `3` | 会审时最多几个技能参与（不含模型本家） |
| `native_voice` | `true` | 会审时是否让不读技能的模型本家作为一方参与 |
| `max_review_rounds` | `2` | 辩论与复审的最大轮数 |
| `exclude` | `[]` | 不调用的技能名，支持 `*` 通配，可写 `插件名:技能名` |
| `extra_paths` | `[]` | 额外扫描的技能目录 |
| `extra_brand_terms` | `[]` | 输出前额外要清除的词（作者笔名、品牌名等） |

对话里的说法示例：

- “孔明，以后显示出处” → `show_sources brief`
- “孔明，给我看完整验证过程” → `show_sources full`
- “孔明，别显示来源了” → `show_sources off`
- “孔明，快一点，别会审了” → 本次按单将；说“以后都这样”则 `mode single`
- “孔明，别用 xxx” → `add exclude xxx`
- “孔明，把 ~/my-skills 也算上” → `add extra_paths ~/my-skills`
