# Skill 数据集使用说明

本文档说明这批 Skill 数据**包含什么、在哪里、怎么取**。

---

## 一、数据是什么

一批 Claude Code Skill 的**索引元数据 + 完整文件包**：

- 每条记录 = 一个 skill（一个 `SKILL.md` 及其 `scripts/`、`references/`、`assets/` 等同目录文件）
- 元数据在 **PostgreSQL** 的 `skills` 表里
- 文件按 skill 放在磁盘上，**用 `skills.id` 作为目录名**，一一对应

覆盖 SkillsMP 与 Skillshub 两个市场的收录结果，含作者、仓库、Star 数、更新时间、内容指纹等信息。

---

## 二、数据规模

| 项目 | 数量 |
|---|---|
| `skills` 表总行数 | **1,616,222** |
| 已落地（`copied = TRUE`，磁盘上有文件） | **1,438,085** |
| 未落地（`extract_status = 'missing'`，**无文件**） | 178,137 |
| 涉及仓库数（`repo` 去重） | 75,731 |
| 涉及作者数（`author` 去重） | 58,925 |
| 有内容指纹的记录（`skill_md5` 非空且非 `__MISSING__`） | 1,374,968 |
| 内容指纹去重后的**唯一内容数** | **843,024** |

> 注意：843,024 ≪ 1,374,968，说明同一份内容被多个路径/快照重复收录。**按内容做分析前请先用 `skill_md5` 去重。**

---

## 三、数据在哪

### 3.1 元数据：PostgreSQL

```
host     : 10.0.0.38
port     : 15432
database : skill
user     : read_user
password : read_user
```

- 版本：PostgreSQL 18.4
- 相关表：`skills`（主表，约 1.76 GB）、`crawl_state`（采集水位线，一般人用不到）
- 非交互使用（脚本里）请带密码环境变量，否则 `psql` 会交互式提示输入：

```bash
export PGPASSWORD='ybasG50m'
# 或
PGPASSWORD='ybasG50m' psql -h 10.0.0.38 -p 15432 -U read_user -d skill -c "select 1;"
```

### 3.2 文件：磁盘目录
10.0.0.196   skills_craw/skills_craw

```
SkillDownloader/data/skills/{skills.id}/
```

- 绝对路径：`/home/user/database/bigdata/workspace/SkillDownloader/data/skills/`
- 目录数 ≈ 1,438,085，与 `copied = TRUE` 的行数一致

单个 skill 目录示例：

```
data/skills/aipoch-medical-research-skills-...-lipinski-rule-filter-skill-md/
├── SKILL.md                            # 主文件，YAML frontmatter 含 name/description/license/author
├── requirements.txt
├── references/
├── scripts/
└── lipinski-rule-filter_audit_result_v2.json
```

```
data/skills/pranavnagrecha-awesomesalesforceskills-...-oauth-redirect-and-domain-strategy-skill-md/
├── SKILL.md
├── references/
├── scripts/
└── templates/
```

```
data/skills/tomevault-io-skills-registry-...-obra-skill-md__1778513451/
├── SKILL.md
└── README.md
```

`SKILL.md` 头部形如：

```markdown
---
name: lipinski-rule-filter
description: Filter compound libraries based on Lipinski's Rule of Five for drug-likeness.
license: MIT
author: AIPOCH
---
```

**许可证信息在 `SKILL.md` 的 frontmatter 里**（`license:` 字段），表里没有单独字段。

---

## 四、怎么取

### 方式 A：只取元数据（推荐先做）

需要 `psql` 或 Python `psycopg2`。

```bash
# 连通性自测
psql -h 10.0.0.38 -p 15432 -U read_user -d skill -c "select count(*) from skills;"
```

导出全量清单（TSV，供后续按需取文件用）：

```bash
psql -h 10.0.0.38 -p 15432 -U postgres -d skill -c "\copy (
    select id, name, author, repo, branch, skill_path,
           stars, forks, updated_at, skill_md5,
           file_count, package_size, source_type
      from skills
     where copied = true
) to 'manifest.tsv' with (format csv, delimiter E'\t', header true)"
```

### 方式 B：按需取单个 skill 的文件

**关键：目录名 = `skills.id`。**

```bash
ID="aipoch-medical-research-skills-scientific-skills-data-analysis-lipinski-rule-filter-skill-md"
ls -a "SkillDownloader/data/skills/$ID"
cat "SkillDownloader/data/skills/$ID/SKILL.md"
```


## 五、`skills` 表字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | text | **主键**。全局唯一，同时就是 `data/skills/` 下的目录名 |
| `name` | text | skill 名称 |
| `author` | text | 作者 / 组织 |
| `description` | text | 描述 |
| `stars` / `forks` | int | 仓库 Star / Fork 数 |
| `updated_at` | bigint | 上游更新时间，Unix 秒 |
| `repo` | text | `owner/repo` |
| `branch` | text | 分支 |
| `skill_path` | text | `SKILL.md` 在仓库内的相对路径 |
| `github_url` | text | 原始 GitHub 目录链接 |
| `github_url_path` | text | 规范化后的 GitHub 目录链接 |
| `copied` | bool | **文件是否已落到磁盘**。取文件前必须 `copied = true` |
| `extract_status` | text | `success` / `pending` / `missing` |
| `file_count` | int | 文件个数（**部分批次为 0，见第六节**） |
| `package_size` | bigint | 目录字节数（**部分批次为 0，见第六节**） |
| `skill_md5` | text | `SKILL.md` 内容的 MD5；`__MISSING__` 表示该目录下没有 `SKILL.md` |
| `source` | text | 采集批次标记 |
| `source_type` | text | `github_crawl`（来自 GitHub 收录） / `skillshub`（来自 Skillshub 市场） |
| `orig_id` | text | 原始平台 id（`skillshub` 批次） |
| `dir_name` | text | 原始目录名（`skillshub` 批次） |
| `snapshot_ts` | bigint | 快照时间，Unix 秒（`skillshub` 批次） |
| `category` | text | 分类（`skillshub` 批次，全部有值） |
| `tags` | text | 标签（`skillshub` 批次，全部有值） |
| `quality_score` | float | 质量分（仅 14,269 行有值，其余为 NULL） |
| `metadata_json` | jsonb | 原始元数据（`skillshub` 批次） |
| `extract_error` | text | 失败原因 |

**索引**：`skills_pkey(id)`、`idx_skills_repo(repo)`、`idx_skills_md5(skill_md5)`、`idx_skills_source_updated(source, updated_at DESC)`、`idx_skills_copied(copied) WHERE NOT copied`。

---

## 六、注意事项（容易踩的坑）

1. **务必过滤 `copied = true`**
   表里有 178,137 行 `extract_status = 'missing'`，这些记录**磁盘上没有文件**（上游仓库已删除或路径失效）。直接按全表取文件会大面积 404。

2. **`file_count` / `package_size` 只在部分批次有值**
   `skillshub` 批次 929,596 行全部为 `0`；`github_crawl` 批次里也有 374,626 行为 `0`。
   用 `package_size > 0` 做过滤会漏掉约 130 万条。**要判断"有没有文件"就只看 `copied`。**

3. **内容去重必须用 `skill_md5`**
   1,374,968 条有指纹的记录只对应 843,024 份唯一内容，重复率约 39%。
   另有 63,094 条指纹为 `__MISSING__`（目录内没有 `SKILL.md`），做内容分析时建议排除。

4. **`id` 有两种形态**
   - GitHub 批次：`{author}-{repo}-{path}-skill-md`
   - Skillshub 批次：`{dir_name}__{snapshot_ts}`，**同一个 skill 会因多次快照产生多行**，按 `orig_id` 或 `dir_name` 聚合才是同一个 skill。

5. **单条记录可能很大**
   存在 `package_size` 超过 100 MB 的记录（含大资产文件）。按需取用，不要无脑全量拉。

6. **编码统一 UTF-8**，`description` / `metadata_json` 中可能含中文。

7. **拷贝时不要整目录全拿，只取这两处**：
   - `data/skills/`（数据集本体）
   - `manifest.tsv`（自行导出）

   同一台机器上的 `data/tmp/`（运行时临时目录）、`data/projects/`（历史遗留的整仓克隆）、`data/SkillMonitor.tar.xz`（约 33 GB 原始归档）、项目根的 `SkillMonitor/`（原始快照目录）**都不属于本数据集**，其中的信息已全部体现在 `skills` 表和 `data/skills/` 里，无需拷贝。

---

## 七、快速上手（30 秒版）

```bash
# 1. 连库确认规模
psql -h 10.0.0.38 -p 15432 -U read_user -d skill \
  -c "select count(*) filter (where copied) as usable, count(*) as total from skills;"

# 2. 随机挑一个 skill 看效果
ID=$(psql -h 10.0.0.38 -p 15432 -U read_user -d skill -tAc \
     "select id from skills where copied order by random() limit 1")
echo "$ID"
ls -a "SkillDownloader/data/skills/$ID"
cat "SkillDownloader/data/skills/$ID/SKILL.md"

# 3. 导出清单
psql -h 10.0.0.38 -p 15432 -U read_user -d skill -c "\copy (select id, name, author, repo, stars, updated_at, skill_md5, source_type from skills where copied) to 'manifest.tsv' with (format csv, delimiter E'\t', header true)"
```

---

## 八、常见查询示例

```sql
-- 按关键词搜 skill（名称 + 描述）
SELECT id, name, author, stars
  FROM skills
 WHERE copied AND (name ILIKE '%pdf%' OR description ILIKE '%pdf%')
 ORDER BY stars DESC NULLS LAST
 LIMIT 50;

-- 按分类取（skillshub 批次）
SELECT id, name, tags, stars
  FROM skills
 WHERE copied AND category = 'data-analysis'
 ORDER BY stars DESC NULLS LAST
 LIMIT 50;

-- Star 最高的 50 个
SELECT id, name, repo, stars, updated_at
  FROM skills
 WHERE copied
 ORDER BY stars DESC NULLS LAST
 LIMIT 50;

-- 内容去重后的唯一条数
SELECT count(DISTINCT skill_md5)
  FROM skills
 WHERE copied AND skill_md5 IS NOT NULL AND skill_md5 <> '__MISSING__';

-- 同一份内容有哪些重复记录
SELECT skill_md5, count(*) AS n, array_agg(id ORDER BY id)[1:3] AS sample_ids
  FROM skills
 WHERE copied AND skill_md5 IS NOT NULL AND skill_md5 <> '__MISSING__'
 GROUP BY skill_md5
HAVING count(*) > 1
 ORDER BY n DESC
 LIMIT 20;

-- 按仓库聚合
SELECT repo, count(*) AS skills, max(stars) AS stars
  FROM skills
 WHERE copied
 GROUP BY repo
 ORDER BY skills DESC
 LIMIT 20;
```

---

## 九、Python 读取示例

```python
import psycopg2

conn = psycopg2.connect(host="10.0.0.38", port="15432",
                        dbname="skill", user="read_user", password="read_user")
cur = conn.cursor()

cur.execute("""
    SELECT id, name, author, stars, updated_at
      FROM skills
     WHERE copied AND category = %s
     ORDER BY stars DESC NULLS LAST
     LIMIT 100
""", ("data-analysis",))

for sid, name, author, stars, updated_at in cur.fetchall():
    path = f"SkillDownloader/data/skills/{sid}/SKILL.md"
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # ... 处理

conn.close()
```

---

## 十、交付清单（把数据给到对方需要的东西）

| 交付物 | 位置 | 说明 |
|---|---|---|
| PostgreSQL 连通信息 | 本文档第 3.1 节 | 元数据主入口 |
| `data/skills/` 目录 | 项目根下 | 1,438,085 个 skill 目录，按 `skills.id` 命名 |
| `manifest.tsv` | 自行按第 4 节导出 | 建议随数据一起给，方便对方核对数量与按需取文件 |
| 本说明文档 | `DATA_HANDOVER.md` | — |
