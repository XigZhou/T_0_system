# 用户认证与用户管理架构设计

生成时间：2026-05-20
适用工作区：/home/ubuntu/T_0_system
状态：已按用户确认的方案记录，等待实施计划确认后编码

## 1. 目标

为现有 A 股 T_0 回测系统增加用户注册、登录、退出、当前用户识别和用户管理能力。所有系统功能必须登录后使用；系统管理员模块和用户管理模块只允许 admin 用户访问。普通访客可以自助注册普通用户。

## 2. 非目标

本次不改动回测、信号质量、每日选股、单股回测、模拟交易、指标计算、表达式解析、Tushare 数据同步等量化核心算法。本次不实现充值、支付、邮箱/短信找回密码、第三方 OAuth 登录。

## 3. 当前系统结构判断

后端入口集中在 overnight_bt/app.py，静态页面由 FastAPI 直接读取 static/*.html 返回，前端 JS 直接调用 /api/*。现有 models.py、股票池模板、模拟交易模块已经有 username 或 stock_pool_username 字段，但当前多处前端硬编码为 admin。data_store/stock_pool_templates.sqlite 已有占位 users 表，但只保存空密码哈希，没有真实认证能力。

## 4. 推荐架构

采用轻量内置用户系统和 HttpOnly Cookie Session。新增 overnight_bt/auth.py，集中负责用户表迁移、密码哈希、session 创建/校验/吊销、当前用户依赖、admin 权限依赖和用户管理服务。overnight_bt/app.py 只在路由边界调用 auth 依赖，不把认证逻辑写进回测引擎模块。

前端新增登录、注册和用户管理页面，并新增共享脚本 static/auth.js。所有页面通过 /api/auth/me 获得当前用户，渲染用户徽标、退出按钮，并隐藏普通用户不可见的 admin 入口。

## 5. 用户模型

用户表继续放在 data_store/stock_pool_templates.sqlite 的 users 表中，以减少运行库数量。表结构在现有字段基础上增量扩展：

- user_id：不可变 UUID，未来充值、订单、额度、会员模块引用它。
- username：登录名，唯一，继续兼容现有股票池和模拟交易的 username 隔离。
- password_hash：密码哈希，不保存明文。
- display_name：展示名称。
-
ole：admin 或 user。
- is_active：是否启用。
- created_at、updated_at、last_login_at、password_updated_at。

默认管理员账号为 admin，但默认密码不写入代码或文档。迁移时如果 admin 不存在则创建；如果存在但 password_hash 为空，仅在服务器设置 T0_ADMIN_DEFAULT_PASSWORD 时补齐密码哈希；如果已设置哈希则不覆盖。

## 6. Session 模型

新增 uth_sessions 表：

- session_id：随机 URL-safe token 的哈希或随机 ID。
- username：关联 users.username。
- created_at、expires_at、last_seen_at。
- user_agent：审计辅助字段。
- is_revoked：退出或管理员禁用后吊销。

浏览器使用 HttpOnly Cookie 保存 session id。业务 API 不接受前端伪造的 username 作为身份依据。

## 7. 权限边界

公开页面和 API：

- /login
- /register
- /api/auth/login
- /api/auth/register
- /api/auth/logout
- /api/auth/me
- /health
- /static/*

登录用户页面和 API：

- /
- /single
- /daily
- /paper
- /paper/templates
- /stock-pools
- /sector
- 普通业务 /api/*

admin 专属页面和 API：

- /admin
- /users
- /api/users/*
- /api/admin/stock-data/daily
- /api/admin/stock-data/indicators
- /api/stock-pools/template/refresh
- /api/stock-pools/jobs
- /api/stock-pools/jobs/{job_id}

未登录访问受保护页面跳转 /login。未登录访问受保护 API 返回 401。非 admin 访问 admin 页面或 API 返回 403。

## 8. 业务用户接入方式

在 pp.py 路由边界解析当前登录用户，并覆盖或注入请求中的用户字段：

- 普通用户的 username、stock_pool_username 自动设为当前登录用户名。
- admin 使用 admin 身份访问系统管理员功能。
- 现有量化模块继续接收已有 Pydantic 请求模型，不直接依赖 auth 模块。

这样用户系统与量化引擎解耦，并复用现有基于 username 的股票池、模拟交易数据隔离。

## 9. 忘记密码策略

密码使用哈希后无法找回原密码，只能重置。第一版策略：

- 普通用户忘记密码，由 admin 在用户管理模块重置密码。
- 已登录用户后续可扩展 修改密码，需要输入旧密码。
- admin 忘记密码，通过服务器侧管理函数或脚本重置，不提供公开找回入口。
- 本次不做邮箱/短信找回；如果后续需要，再新增绑定邮箱/手机号、password_reset_tokens 表和发送通道。

## 10. 充值扩展预留

本次不实现充值，但通过 user_id 预留资金账户主键。未来充值模块可单独新增：

- illing_accounts：关联 user_id。
-
echarge_orders：充值订单、金额、渠道、状态、回调信息。
- illing_transactions：资金流水。
- user_entitlements：会员、额度、功能权限和到期时间。

充值模块不放进 uth.py，只引用 users.user_id，保持认证和计费解耦。

## 11. Migration Plan

1. 备份或至少确认 data_store/stock_pool_templates.sqlite 可读。
2. 执行 init_auth_db()：对 users 表执行 ALTER TABLE ADD COLUMN 补齐 user_id、
ole、is_active、last_login_at、password_updated_at。
3. 对已有 users 行补齐 user_id，空
ole 默认为 user，admin 强制为 admin。
4. 创建 uth_sessions 表和索引。
5. 初始化 admin：不存在则创建；存在但无密码哈希则设置默认密码哈希。
6. 不删除任何旧表、旧列、股票池模板、行情数据或模拟交易账本。
7. 回滚时可移除路由依赖，旧业务数据仍按 admin 或历史 username 读取。

## 12. 影响范围

新增文件：

- overnight_bt/auth.py
- static/login.html
- static/register.html
- static/users.html
- static/auth.js
- static/users.js
- 	ests/test_auth.py

修改文件：

- overnight_bt/app.py
- overnight_bt/models.py
- static/*.html
- static/*.js
- static/style.css
- 	ests/test_api_integration.py
- 必要时 docs/system-documentation.md

明确不修改：

- overnight_bt/backtest.py
- overnight_bt/signal_quality.py
- overnight_bt/expressions.py
- overnight_bt/processing.py
- overnight_bt/indicators.py

## 13. 风险控制

- 不影响已有回测结果：不改回测算法和指标计算。
- API 行为变化：业务 API 需要登录 Cookie，测试需增加认证上下文或直接调用未包装的业务函数。
- 数据库结构变化：只增量添加认证字段和 session 表，不改股票池、行情、模拟交易主表语义。
- 用户隔离变化：普通用户默认只看到自己的股票池模板和模拟账户。

## 14. 验证计划

- python -m py_compile overnight_bt/app.py overnight_bt/auth.py
- pytest tests/test_auth.py -v
- pytest tests/test_api_integration.py -v
- 现有前端 Node payload 测试
- FastAPI 冒烟：登录页、注册页、未登录跳转、普通用户访问普通页面、普通用户访问 admin 被拒绝、admin 访问 /admin 和 /users 成功、/health 保持可用。

## 15. 自检结果

本文档无 TBD/TODO；已明确用户注册口径、忘记密码策略、充值扩展预留、迁移方式、权限边界和不修改的量化核心模块。范围适合单次增量实施，不需要大规模重构。
