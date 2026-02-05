# Provider Factory Pattern Design

> Phase 5: Provider 系统重构 - 用户可注册自定义 Provider

## 需求

1. 统一 provider 接口（抽象基类 + 工厂模式）
2. 用户可通过 UI 添加自定义 provider（OpenAI 兼容 API）
3. 配置存储在 `~/.youresearch/providers.json`
4. 后端 API 支持 CRUD 操作

## 数据结构

```json
{
  "providers": {
    "my-ollama": {
      "name": "my-ollama",
      "display_name": "My Ollama",
      "base_url": "http://localhost:11434/v1",
      "api_key": "",
      "models": ["llama3", "codellama", "mistral"],
      "default_model": "llama3"
    }
  },
  "active_provider": "openrouter"
}
```

## 文件结构

```
backend/agent/providers/
├── __init__.py          # 导出 get_provider_manager
├── base.py              # 抽象基类 ModelProvider
├── openai_compatible.py # OpenAI 兼容实现
├── openrouter.py        # 内置 OpenRouter（改造）
├── manager.py           # ProviderManager
└── config.py            # 配置文件读写
```

## API 端点

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/providers | 列出所有 provider |
| POST | /api/providers | 添加自定义 provider |
| PUT | /api/providers/{name} | 更新 provider |
| DELETE | /api/providers/{name} | 删除 provider |
| POST | /api/providers/active | 设置当前 provider |
| POST | /api/providers/{name}/test | 测试连接 |

## 实现步骤

1. 创建 `base.py` - 抽象基类
2. 创建 `openai_compatible.py` - 通用实现
3. 创建 `config.py` - 配置读写
4. 创建 `manager.py` - 管理器
5. 改造 `openrouter.py` - 继承基类
6. 更新 `__init__.py` - 导出
7. 添加 API 端点到 `main.py`
8. 更新 `pydantic_agent.py` - 使用 manager
