# AAgent

过渡中,有点混乱,超级缝合怪,集各家平台之大成,强调弹性、自定义、易于调试   
就目前的大换血而言,这套架构的可扩展性非常强    

TODO:
- workflow 解析json
- workflow 列表组件

## 快速启动
0. QQ需配置NapNeko/NapCatQQ!
1. 安装 Docker Desktop 与 Docker Compose;
2. 复制环境变量模板并填写所有 `replace-me`;
3. 构建并启动服务;

```powershell
Copy-Item .env.example .env
# 编辑 .env
docker compose up --build -d
docker compose logs -f agent qqbot
```

WebUI 地址:`http://localhost:8081`。完整变量说明、端口和安全检查见[配置与部署](docs/04-配置与部署.md)。

## 安全

不要提交 `.env`、API Key、访问 Token 或 `data/`。曾出现在源码或 Git 历史中的凭据必须先吊销,再从服务商处生成新凭据。

## 彩蛋

agent/test.py