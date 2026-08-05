# AI 分析配置增强（连通性测试 + 模型列表）Spec

## Why
当前 AI 分析配置只能手填 API Key / 模型名 / API 地址，用户无法验证配置是否正确、无法快速了解服务端支持的模型，配置错误只能等实际分析时才发现。

## What Changes
- 后端新增 AI 连通性测试接口：`POST /api/ai/test-connection`
- 后端新增 AI 模型列表获取接口：`POST /api/ai/models`
- 前端设置页 AI 分析配置卡片：
  - 新增"测试连通性"按钮，展示测试结果（成功/失败、耗时、错误详情）
  - 模型输入改为下拉选择 + "手动输入"选项，配"刷新模型列表"按钮

## Impact
- Affected specs: 无（新功能，独立变更）
- Affected code:
  - `app/api/ai_routes.py` — 新增两个接口
  - `app/services/ai_analyzer.py` — 新增连通性测试和模型列表方法
  - `app/templates/settings.html` — AI 配置卡片 UI 改造

## ADDED Requirements

### Requirement: AI 连通性测试
系统 SHALL 提供 AI 配置连通性测试能力，验证 API Key、API 地址、模型名三者组合是否可用。

#### Scenario: 测试成功
- **WHEN** 用户在设置页填入有效的 API Key / API 地址 / 模型名，点击"测试连通性"
- **THEN** 系统调用 AI 服务的 chat/completions 接口（最小化请求），返回成功、HTTP 状态码和耗时

#### Scenario: 测试失败
- **WHEN** API Key 无效、地址不可达或模型名错误
- **THEN** 系统返回明确的失败原因（鉴权失败/连接超时/模型不存在/网络错误），前端以醒目样式展示

#### Scenario: 使用未保存的临时配置
- **WHEN** 用户在表单中修改了配置但未点击"保存配置"就点"测试连通性"
- **THEN** 系统使用表单中的临时值测试，不要求先保存

### Requirement: AI 模型列表获取
系统 SHALL 能从 AI 服务端自动获取可用模型列表并填充到设置页。

#### Scenario: 获取成功
- **WHEN** 用户填入 API Key / API 地址后点击"获取模型列表"
- **THEN** 系统请求 `{base_url}/models` 端点，将返回的模型 id 列表填充到模型下拉框

#### Scenario: 获取失败
- **WHEN** 地址不可达、Key 无效或服务端不支持 /models 端点
- **THEN** 系统展示错误提示，模型下拉框保留"手动输入"选项，用户仍可手动填写模型名

#### Scenario: 手动输入兜底
- **WHEN** 服务端不支持模型列表接口，或用户想使用自定义模型名
- **THEN** 模型下拉框提供"手动输入"选项，选中后可自由填写模型名

## MODIFIED Requirements

### Requirement: 设置页 AI 分析配置卡片
[原功能：手填 AI API Key / 模型名 / API 地址，保存到 Setting]
修改为：模型名改为下拉框（自动获取 + 手动输入兜底），新增"测试连通性"、"获取模型列表"两个操作按钮，测试结果在页面内联展示，不影响原有保存逻辑。

## REMOVED Requirements

（无）
