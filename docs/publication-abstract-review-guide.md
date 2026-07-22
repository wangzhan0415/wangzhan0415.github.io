# Publication Abstract 候选数据审核指南

本流程只采集候选摘要供人工审核，不会自动写入网站 Publication 内容。

## 运行工作流

1. 在 GitHub 仓库打开 **Actions**。
2. 选择 **Collect Publication Abstract Candidates**。
3. 点击 **Run workflow**。
4. `stable_id` 可留空以处理全部 Publication，或填写如 `J2026-01` 只测试单篇。
5. 默认不启用 `include_publisher_pages`；只有需要访问 DOI 官方落地页公开 HTML 元数据时才启用。
6. `delay_seconds` 默认 `1.0`，用于控制外部请求间隔。

## 下载并审核 Artifact

工作流会上传 `publication-abstract-candidates-${{ github.run_number }}`，保留 14 天。下载后打开：

- `abstract_candidates_review.csv`
- `abstract_candidates.json`
- `summary.md`
- `review_instructions.md`
- `failed_records.csv`
- `abstracts/<stable_id>.md`

## CSV 审核规则

1. 打开 `abstract_candidates_review.csv`。
2. 逐条比较标题、DOI 和 Abstract。
3. 在 `decision` 列填写 `approve` 或 `reject`。
4. 不要修改 `stable_id`、`doi` 和 `local_title`。
5. `replacement_abstract` 仅用于人工修正明显的编码或排版问题。
6. 保存为 UTF-8 CSV。
7. 将审核后的 CSV 交给 Codex 执行导入。

`decision` 默认留空；工作流不会自动填写 `approve`。

## 导入安全说明

审核后导入脚本为 `scripts/apply_approved_publication_abstracts.py`，默认 dry-run。只有显式传入 `--apply` 时才会写入 Publication 文件，并且只允许写入：

- `abstract`
- `abstract_source`
- `abstract_source_url`
- `abstract_retrieved_at`
- `abstract_verified`

脚本会拒绝 DOI 不一致、标题不一致、空摘要、`confidence` 为 `low` 或 `rejected`、以及非 `approve` 决策的记录。
