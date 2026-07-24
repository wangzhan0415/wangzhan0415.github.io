---
title: "面向巡检应用的 ＲGBD 相机主动视角矫正方法"
authors:
  - "韩昊一"
  - "孟瑜炜"
  - "贾晓燕"
  - "鲁鼎"
  - "王战"
  - "徐辰楠"
  - "俞荣栋"
authors_display: "韩昊一; 孟瑜炜; 贾晓燕; 鲁鼎; 王战; 徐辰楠; 俞荣栋"
authors_complete: true
authors_source: "reviewed-publication-pdf"
abstract: |-
  在机器人视觉巡检任务中，移动平台固有的定位误差会导致相机视角发生偏移，从而严重影响后续图像分析的可靠性。为解决此问题，提出一种主动视角矫正方法。利用 OＲB 特征和 GMS 统计模型在 2D 图像域进行快速、鲁棒特征匹配; 结合深度信息建立稀疏的 3D 对应关系，并通过基于 ＲANSAC 的点到点 ICP 获得一个全局稳健的初始位姿; 最后，利用稀疏到稠密的点到平面 ICP 算法，对位姿进行精确优化。通过将该算法集成至包含离线模板标注和在线多模态引导的完整应用系统中，形成了可主动补偿位姿偏差、引导用户或机器人精确对准目标视角的解决方案。实验结果表明: 该方法在保证实时性的前提下，达到了像素级的图像重定位精度，即使面对仅 20 像素×20 像素的微小巡检目标，仍能维持 0. 89 以上的平均结构相似度，证明了该方法在工业巡检应用中的有效性和实用性，具有较高的工程应用价值。
abstract_source: "reviewed-publication-pdf"
keywords:
  - "机器人巡检"
  - "位姿估计"
  - "主动视角矫正"
  - "点云配准"
keywords_source: "reviewed-publication-pdf"
keywords_status: "verified"
metadata_status: "reviewed"
metadata_retrieved_at: "2026-07-23"
author_details: []
date: "2025-12-02T00:00:00Z"
display_date: "Dec 2025"
publication_type: "Journal Article"
publication: "机床与液压"
doi: "10.3969/j.issn.1001-3881.2025.24.031"
url_doi: "https://doi.org/10.3969/j.issn.1001-3881.2025.24.031"
subjects: []
subjects_source: ""
publisher: ""
publisher_source: ""
issn: []
eissn: ""
volume: ""
issue: ""
pages: ""
article_number: ""
landing_page: ""
language: ""
jcr:
  edition: ""
  metric_year: ""
  jif: null
  categories: []
  source: ""
  verified_at: ""
stable_id: "J2025-01"
featured: true
draft: false
display_year: "2025"
display_month: "Dec"
---
