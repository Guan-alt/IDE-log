# 多记录批量AI测试报告 Spec

## Why

当前系统只能对单条OTA记录进行AI分析，无法跨多条记录生成综合测试报告。用户需要选择多条测试记录，让AI综合分析后生成一份汇总测试报告，用于评估整体OTA质量。

## What Changes

* 历史记录表格新增复选框列，支持选择多条记录

* 新增"生成测试报告"按钮，选中记录后点击触发批量AI分析

* 后端新增 `/api/ai/batch-report` 接口，接收多个 record\_id，汇总所有记录数据后调用AI生成综合报告

* 报告在弹窗中展示，支持 Markdown 渲染

## Impact

* Affected code: `app/api/ai_routes.py` — 新增批量报告接口

* Affected code: `app/services/ai_analyzer.py` — 新增批量分析方法

* Affected code: `app/templates/records.html` — 新增复选框列和批量报告按钮

* Affected code: `app/static/css/style.css` — 复选框和批量按钮样式

## ADDED Requirements

### Requirement: 批量选择记录

历史记录表格每行前新增复选框，支持全选/取消全选当前页记录。选中记录后页面底部显示"生成测试报告"按钮。

#### Scenario: 选择多条记录生成报告

* **WHEN** 用户勾选多条记录并点击"生成测试报告"

* **THEN** 系统收集所有选中记录的ID，提交到后端批量分析接口

* **AND** 弹窗显示分析进度，AI综合所有记录数据生成一份测试报告

* **AND** 报告以Markdown格式在弹窗中展示

#### Scenario: 未选择记录时点击生成

* **WHEN** 用户未勾选任何记录点击"生成测试报告"

* **THEN** 提示"请至少选择一条记录"

### Requirement: 批量AI测试报告内容

AI收到的汇总数据包含每条记录的设备SN、来源/目标版本、结果、耗时、失败原因、AI分析结果（如有）。AI输出综合测试报告，包含整体成功率统计、常见失败原因、版本兼容性评估、改进建议等。

#### Scenario: 报告生成成功

* **WHEN** 后端收集到多条记录数据并调用AI

* **THEN** AI返回包含统计分析和建议的综合报告

* **AND** 报告在弹窗中以Markdown渲染展示

#### Scenario: AI接口未配置或调用失败

* **WHEN** AI API Key未配置或调用超时

* **THEN** 弹窗显示失败原因提示

