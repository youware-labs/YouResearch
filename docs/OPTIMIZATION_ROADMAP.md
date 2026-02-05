# YouResearch Agent 优化路径

> 基于 2026-02-04 架构审查，按优先级排序的改进计划

## 当前状态概览

| 维度 | 现状 | 目标 |
|------|------|------|
| 安全性 | 🟡 6/10 | 9/10 |
| 可靠性 | 🟡 6/10 | 9/10 |
| 可扩展性 | 🟡 5/10 | 8/10 |
| 可维护性 | 🟢 7/10 | 9/10 |
| 性能 | 🟡 6/10 | 8/10 |

---

## Phase 1: 安全加固（立即）

### 1.1 加固 Fallback API Key 机制
- **文件**: `backend/agent/providers/openrouter.py`
- **背景**: 内置 API Key 用于让用户零配置使用免费模型，这是有意设计
- **风险**: 密钥可能被滥用，导致配额耗尽
- **加固措施**:
  ```python
  # 1. 在 OpenRouter 后台限制该 key 只能访问免费模型
  FREE_MODELS = [
      "meta-llama/llama-3.2-3b-instruct:free",
      "google/gemma-2-9b-it:free",
      "mistralai/mistral-7b-instruct:free",
      # ... 其他免费模型
  ]

  # 2. 代码中检查：fallback key 只能用免费模型
  def get_model(model_id: str, api_key: str | None = None):
      using_fallback = api_key is None
      if using_fallback:
          api_key = INTERNAL_OPENROUTER_API_KEY
          if model_id not in FREE_MODELS:
              raise ValueError(
                  f"Model {model_id} requires your own API key. "
                  f"Set OPENROUTER_API_KEY or use a free model."
              )
      ...

  # 3. 添加速率限制防止滥用
  FALLBACK_RATE_LIMIT = 10  # 每分钟 10 次
  ```
- [ ] OpenRouter 后台设置 key 限制
- [ ] 代码添加免费模型白名单检查
- [ ] 添加 fallback key 专用速率限制

### 1.2 添加路径安全检查
- **文件**: `backend/agent/pydantic_agent.py`
- **问题**: 未检查符号链接攻击
- **修复**:
  ```python
  def validate_path(filepath: str, project_path: str) -> Path:
      full_path = (Path(project_path) / filepath).resolve()
      # 检查符号链接
      if full_path.is_symlink():
          raise ValueError("Symbolic links not allowed")
      # 检查路径逃逸
      if not str(full_path).startswith(str(Path(project_path).resolve())):
          raise ValueError("Path escapes project directory")
      return full_path
  ```
- [ ] 完成

### 1.3 添加 API 速率限制
- **文件**: 新建 `backend/agent/rate_limiter.py`
- **实现**:
  ```python
  from asyncio import Semaphore
  from time import time

  class RateLimiter:
      def __init__(self, calls_per_minute: int = 60):
          self.calls_per_minute = calls_per_minute
          self.semaphore = Semaphore(calls_per_minute)
          self.call_times: list[float] = []

      async def acquire(self):
          # 滑动窗口限流
          ...
  ```
- [ ] 完成

---

## Phase 2: 数据持久化（本周）

### 2.1 会话存储迁移到 SQLite
- **文件**: `backend/agent/streaming.py`
- **问题**: `_session_histories` 使用内存字典，重启丢失
- **方案**:
  ```python
  # 新建 backend/services/session_store.py
  import sqlite3
  from pathlib import Path

  class SessionStore:
      def __init__(self, db_path: str = "~/.youresearch/sessions.db"):
          self.db = sqlite3.connect(Path(db_path).expanduser())
          self._init_schema()

      def save(self, session_id: str, history: list):
          ...

      def load(self, session_id: str) -> list:
          ...

      def cleanup_expired(self, max_age_hours: int = 24):
          ...
  ```
- [ ] 完成

### 2.2 计划持久化
- **文件**: `backend/agent/planning.py`
- **问题**: `PlanManager._plans` 使用内存字典
- **方案**: 复用 SessionStore 或单独存储
- [ ] 完成

### 2.3 添加会话过期清理
- **实现**: 后台任务定期清理过期会话
  ```python
  async def cleanup_task():
      while True:
          await asyncio.sleep(3600)  # 每小时
          session_store.cleanup_expired(max_age_hours=24)
  ```
- [ ] 完成

---

## Phase 3: 错误处理标准化（第2周）

### 3.1 统一错误模型
- **文件**: 新建 `backend/agent/errors.py`
- **实现**:
  ```python
  from enum import Enum
  from dataclasses import dataclass

  class ErrorCode(Enum):
      FILE_NOT_FOUND = "FILE_NOT_FOUND"
      PERMISSION_DENIED = "PERMISSION_DENIED"
      PATH_ESCAPE = "PATH_ESCAPE"
      COMPILATION_FAILED = "COMPILATION_FAILED"
      API_ERROR = "API_ERROR"
      TIMEOUT = "TIMEOUT"
      INVALID_INPUT = "INVALID_INPUT"

  @dataclass
  class ToolError(Exception):
      code: ErrorCode
      message: str
      details: dict | None = None

  @dataclass
  class ToolResult:
      success: bool
      data: Any = None
      error: ToolError | None = None
  ```
- [ ] 完成

### 3.2 重构所有工具的错误处理
- **文件**: `backend/agent/pydantic_agent.py`
- **改动**: 每个 `@aura_agent.tool` 使用统一的 try-except 模式
  ```python
  @aura_agent.tool
  async def read_file(ctx: RunContext[AuraDeps], filepath: str) -> str:
      try:
          path = validate_path(filepath, ctx.deps.project_path)
          return path.read_text(encoding="utf-8")
      except FileNotFoundError:
          raise ToolError(ErrorCode.FILE_NOT_FOUND, f"File not found: {filepath}")
      except PermissionError:
          raise ToolError(ErrorCode.PERMISSION_DENIED, f"Cannot read: {filepath}")
  ```
- [ ] 完成

### 3.3 添加结构化日志
- **文件**: 新建 `backend/agent/logging.py`
- **依赖**: `structlog`
- **实现**:
  ```python
  import structlog

  def setup_logging():
      structlog.configure(
          processors=[
              structlog.processors.TimeStamper(fmt="iso"),
              structlog.processors.JSONRenderer()
          ]
      )

  logger = structlog.get_logger()

  # 使用
  logger.info("tool_called", tool="read_file", filepath=filepath)
  logger.error("tool_failed", tool="edit_file", error=str(e))
  ```
- [ ] 完成

---

## Phase 4: HITL 重构（第3周）

### 4.1 非阻塞审批模式
- **文件**: `backend/agent/hitl.py`
- **问题**: 当前 `request_approval()` 阻塞等待最多 5 分钟
- **新设计**:
  ```python
  class HITLManager:
      async def request_approval(self, ...) -> str:
          """返回 approval_id，不阻塞"""
          approval_id = str(uuid4())
          self._pending[approval_id] = ApprovalRequest(...)
          # 通过 SSE 通知前端
          await self._notify_frontend(approval_id)
          return approval_id

      async def check_status(self, approval_id: str) -> ApprovalStatus:
          """前端轮询或 WebSocket 推送"""
          return self._pending[approval_id].status

      async def submit_decision(self, approval_id: str, approved: bool):
          """前端提交决定"""
          request = self._pending[approval_id]
          request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
          request.event.set()
  ```
- [ ] 完成

### 4.2 工具执行流程改造
- **改动**: 工具检测到需要审批时，暂停并返回 pending 状态
  ```python
  @aura_agent.tool
  async def edit_file(ctx, filepath: str, old: str, new: str) -> str:
      if ctx.deps.hitl_manager:
          approval_id = await ctx.deps.hitl_manager.request_approval(
              tool_name="edit_file",
              args={"filepath": filepath, "old": old, "new": new}
          )
          # 返回 pending 状态，前端处理
          return f"PENDING_APPROVAL:{approval_id}"
      # 无 HITL 直接执行
      ...
  ```
- [ ] 完成

### 4.3 前端审批 UI 改进
- **文件**: `app/components/HITLApprovalModal.tsx`
- **改动**:
  - 显示 diff 视图
  - 支持批量审批
  - 添加"始终允许此类操作"选项
- [ ] 完成

---

## Phase 5: Provider 系统重构（第4周）

### 5.1 Provider 工厂模式
- **文件**: 重构 `backend/agent/providers/`
- **实现**:
  ```python
  # backend/agent/providers/factory.py
  from abc import ABC, abstractmethod

  class ModelProvider(ABC):
      @abstractmethod
      def get_model(self, model_id: str) -> Any:
          ...

  class ProviderFactory:
      _providers: dict[str, type[ModelProvider]] = {}

      @classmethod
      def register(cls, name: str):
          def decorator(provider_cls):
              cls._providers[name] = provider_cls
              return provider_cls
          return decorator

      @classmethod
      def create(cls, name: str, config: dict) -> ModelProvider:
          if name not in cls._providers:
              raise ValueError(f"Unknown provider: {name}")
          return cls._providers[name](config)

  # 注册 providers
  @ProviderFactory.register("openrouter")
  class OpenRouterProvider(ModelProvider):
      ...

  @ProviderFactory.register("dashscope")
  class DashScopeProvider(ModelProvider):
      ...
  ```
- [ ] 完成

### 5.2 修复 Haiku/Opus 模型配置
- **问题**: 当前全部降级到 Sonnet
- **修复**:
  ```python
  MODELS = {
      "default": "anthropic/claude-sonnet-4",
      "haiku": "anthropic/claude-3-5-haiku-20241022",  # 真正的 Haiku
      "opus": "anthropic/claude-opus-4",  # 真正的 Opus
  }
  ```
- [ ] 完成

### 5.3 添加模型回退机制
- **实现**:
  ```python
  async def call_with_fallback(primary: str, fallback: str, **kwargs):
      try:
          return await call_model(primary, **kwargs)
      except RateLimitError:
          logger.warning("rate_limited", model=primary, fallback=fallback)
          return await call_model(fallback, **kwargs)
  ```
- [ ] 完成

---

## Phase 6: 工具系统插件化（第5-6周）

### 6.1 工具注册表
- **文件**: 新建 `backend/agent/tools/registry.py`
- **实现**:
  ```python
  class ToolRegistry:
      _instance = None

      def __init__(self):
          self._tools: dict[str, ToolDefinition] = {}

      @classmethod
      def get(cls) -> "ToolRegistry":
          if cls._instance is None:
              cls._instance = cls()
          return cls._instance

      def register(self, name: str, description: str, category: str):
          def decorator(func):
              self._tools[name] = ToolDefinition(
                  name=name,
                  description=description,
                  category=category,
                  handler=func
              )
              return func
          return decorator

      def get_tools_by_category(self, category: str) -> list[ToolDefinition]:
          return [t for t in self._tools.values() if t.category == category]
  ```
- [ ] 完成

### 6.2 工具按类别拆分
- **目录结构**:
  ```
  backend/agent/tools/
  ├── __init__.py
  ├── registry.py
  ├── file_tools.py      # read_file, edit_file, write_file, ...
  ├── latex_tools.py     # compile_latex, check_syntax, ...
  ├── research_tools.py  # search_arxiv, read_pdf, ...
  ├── planning_tools.py  # plan_task, complete_step, ...
  └── writing_tools.py   # analyze_structure, add_citation, ...
  ```
- [ ] 完成

### 6.3 动态工具加载
- **实现**: 支持从配置文件启用/禁用工具
  ```yaml
  # config/tools.yaml
  enabled_tools:
    - file_tools
    - latex_tools
    - research_tools
  disabled_tools:
    - planning_tools  # 可选禁用
  ```
- [ ] 完成

---

## Phase 7: 可观测性（第7-8周）

### 7.1 指标收集
- **依赖**: `prometheus_client`
- **实现**:
  ```python
  from prometheus_client import Counter, Histogram

  TOOL_CALLS = Counter("tool_calls_total", "Tool calls", ["tool", "status"])
  TOOL_LATENCY = Histogram("tool_latency_seconds", "Tool latency", ["tool"])
  LLM_CALLS = Counter("llm_calls_total", "LLM API calls", ["provider", "model"])
  LLM_TOKENS = Counter("llm_tokens_total", "Tokens used", ["provider", "type"])
  ```
- [ ] 完成

### 7.2 分布式追踪
- **依赖**: `opentelemetry`
- **实现**:
  ```python
  from opentelemetry import trace

  tracer = trace.get_tracer("youresearch")

  @aura_agent.tool
  async def read_file(ctx, filepath: str) -> str:
      with tracer.start_as_current_span("read_file") as span:
          span.set_attribute("filepath", filepath)
          ...
  ```
- [ ] 完成

### 7.3 健康检查端点
- **文件**: `backend/main.py`
- **实现**:
  ```python
  @app.get("/health")
  async def health():
      return {
          "status": "healthy",
          "version": VERSION,
          "uptime": get_uptime(),
          "active_sessions": len(session_store.active()),
          "pending_approvals": hitl_manager.pending_count()
      }

  @app.get("/metrics")
  async def metrics():
      return generate_latest()
  ```
- [ ] 完成

---

## Phase 8: 性能优化（第9-10周） ✅ COMPLETED

### 8.1 连接池管理 ✅
- **文件**: `backend/services/connection_manager.py`
- **实现**:
  ```python
  class ConnectionManager:
      def __init__(self):
          self._clients: dict[str, ManagedClient] = {}

      async def get_client(self, base_url: str) -> httpx.AsyncClient:
          # Pooled client with limits and cleanup
          ...

      async def cleanup_idle(self, max_idle_seconds: int = 300) -> int:
          # Auto-cleanup idle connections
          ...

      async def close_all(self):
          for client in self._clients.values():
              await client.aclose()
  ```
- [x] 完成

### 8.2 消息压缩优化 ✅
- **文件**: `backend/agent/compression.py`
- **改进**:
  - [x] 使用 tiktoken 精确计算 token（带 fallback）
  - [x] 添加压缩失败的多级回退策略（LLM → 提取式 → 基础）
  - [x] 缓存压缩结果（LRU cache）
- [x] 完成

### 8.3 并发控制 ✅
- **文件**: `backend/agent/concurrency.py`
- **实现**:
  ```python
  MAX_CONCURRENT_COMPILATIONS = 3
  compilation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_COMPILATIONS)

  @aura_agent.tool
  async def compile_latex(ctx, ...):
      async with compilation_semaphore:
          ...
  ```
- **功能**:
  - 编译并发限制 (max 3)
  - API 调用限制 (max 10)
  - 文件操作限制 (max 20)
  - 子代理限制 (max 5)
  - 统计信息和监控端点 `/api/performance`
- [x] 完成

---

## Phase 9: 测试覆盖（持续）

### 9.1 单元测试
- **目标覆盖率**: 80%
- **重点**:
  - [ ] 所有工具函数
  - [ ] Provider 逻辑
  - [ ] 错误处理路径
  - [ ] 路径验证

### 9.2 集成测试
- **重点**:
  - [ ] Agent 完整对话流程
  - [ ] HITL 审批流程
  - [ ] Subagent 委托
  - [ ] 会话持久化

### 9.3 端到端测试
- **重点**:
  - [ ] 前端到后端完整流程
  - [ ] Vibe 研究模式
  - [ ] LaTeX 编译

---

## 里程碑时间线

```
Week 1  [====================] Phase 1: 安全加固
Week 2  [====================] Phase 2: 数据持久化
Week 3  [====================] Phase 3: 错误处理
Week 4  [====================] Phase 4: HITL 重构
Week 5  [==========          ] Phase 5: Provider 重构
Week 6  [          ==========] Phase 6: 工具插件化 (1/2)
Week 7  [====================] Phase 6: 工具插件化 (2/2)
Week 8  [==========          ] Phase 7: 可观测性 (1/2)
Week 9  [          ==========] Phase 7: 可观测性 (2/2)
Week 10 [====================] Phase 8: 性能优化
```

---

## 风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Fallback API Key 被滥用 | 中 | 限制只能用免费模型 + 速率限制 |
| 持久化迁移数据丢失 | 中 | 先双写，验证后切换 |
| HITL 重构影响用户体验 | 中 | 灰度发布，保留旧模式 |
| 工具重构引入 bug | 中 | 充分测试，逐步迁移 |

---

## 成功指标

| 指标 | 当前 | 目标 | 衡量方式 |
|------|------|------|----------|
| Fallback Key 滥用率 | 未知 | <1% | 监控异常调用 |
| 会话丢失率 | ~100% (重启) | <1% | 监控 |
| 工具错误处理覆盖 | 60% | 100% | 代码审查 |
| HITL 超时率 | 未知 | <5% | 指标 |
| 测试覆盖率 | 未知 | >80% | CI |
| P95 响应延迟 | 未知 | <3s | 指标 |

---

## 附录：相关文件清单

```
backend/
├── agent/
│   ├── pydantic_agent.py    # 主 agent，需重构工具
│   ├── prompts.py           # 系统提示
│   ├── streaming.py         # 会话存储需迁移
│   ├── compression.py       # 需优化
│   ├── hitl.py              # 需重构为非阻塞
│   ├── planning.py          # 需持久化
│   ├── steering.py          # 需改进优先级队列
│   ├── providers/
│   │   ├── openrouter.py    # 需加固 fallback key 机制
│   │   └── dashscope.py     # OK
│   ├── subagents/
│   │   ├── base.py          # OK
│   │   ├── research.py      # 需改进错误处理
│   │   ├── compiler.py      # OK
│   │   ├── planner.py       # OK
│   │   └── writing.py       # OK
│   └── tools/               # 待创建，工具拆分
└── services/
    ├── docker.py            # OK
    ├── project.py           # OK
    └── session_store.py     # 待创建
```
