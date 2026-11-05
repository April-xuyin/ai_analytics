# ECS 迁移部署手册

## 1. 适用范围

当前项目已在 Mac 上通过 Docker Compose 完成本地生产模拟。迁移到 ECS 不改变问数核心代码，只改变运行机器、入口端口、云网络和密钥配置。

```text
浏览器
  → ECS 安全组 80/443
  → Nginx 容器
  → FastAPI 容器 8000（仅 Docker 内网）
  → DeepSeek API + MaxCompute
```

本手册是可执行的迁移方案，不代表项目已经实际购买 ECS 或完成公网部署。

## 2. 推荐资源

- 地域：华南 1（深圳），与 MaxCompute Project 同地域；
- 系统：Ubuntu 22.04 64 位；
- 规格：低并发演示可使用 2 核 2 GiB，正式多人使用建议至少 2 核 4 GiB；
- 系统盘：40～60 GiB；
- 公网 IP：首次部署和 Web 访问需要；
- 付费：只做迁移验证时使用按量实例并在验收后释放，长期运行再选择包年包月。

## 3. 安全组

| 端口 | 来源 | 用途 |
|---|---|---|
| 22 | 仅管理员当前公网 IP `/32` | SSH 运维 |
| 80 | 业务访问来源；演示时可临时开放公网 | HTTP |
| 443 | 业务访问来源；配置域名和证书后开放 | HTTPS |

不要开放 8000 或 8080。FastAPI 的 8000 只在 Docker 网络内暴露。

## 4. 安装 Docker

SSH 登录 Ubuntu 后执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

退出 SSH 后重新登录，再验证：

```bash
docker version
docker compose version
```

## 5. 上传项目

推荐从私有 Git 仓库拉取代码；也可以从本地使用 `scp` 上传。服务器示例目录：

```bash
sudo mkdir -p /opt/ai-analytics
sudo chown "$USER":"$USER" /opt/ai-analytics
git clone <你的私有仓库地址> /opt/ai-analytics
cd /opt/ai-analytics/ai_analytics
mkdir -p logs
```

真实数据、`.env` 和访问密钥不得提交到 Git。

## 6. 配置生产环境变量

在服务器的 `ai_analytics/.env` 中填写：

```env
QUERY_ENGINE=maxcompute
NGINX_PORT=80

DEEPSEEK_API_KEY=<服务器专用密钥>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

MAXCOMPUTE_PROJECT=ai_analytics_project
MAXCOMPUTE_REGION=cn-shenzhen
MAXCOMPUTE_ENDPOINT=<控制台提供的云产品互联Endpoint或公网Endpoint>
MAXCOMPUTE_ACCESS_ID=<只读RAM用户AccessKey ID>
MAXCOMPUTE_ACCESS_KEY=<只读RAM用户AccessKey Secret>
MAXCOMPUTE_QUERY_TIMEOUT_SECONDS=60

API_AUTH_TOKEN=<管理员随机长令牌>
OPERATOR_API_TOKEN=<运营随机长令牌>
OPERATOR_SHOPS=<授权店铺，多个使用英文逗号分隔>
```

然后限制文件权限：

```bash
chmod 600 .env
```

同地域优先使用 MaxCompute 控制台展示的云产品互联 Endpoint；如果当前账号或网络不支持，则使用已验证的公网 Endpoint。不要凭文档猜 Endpoint，必须以对应 Project 控制台显示值为准。

MaxCompute RAM 用户至少需要提交查询实例、查看实例状态和读取白名单表的权限，不授予建表、删表、写入或项目管理权限。

## 7. 启动与验收

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1/health
```

预期两个容器均为 `healthy`。再从本地浏览器访问：

```text
http://<ECS公网IP>/
```

按以下顺序验收：

1. `/health` 返回 `{"status":"ok"}`；
2. 无令牌问数返回 401；
3. 管理员令牌能查询跨店汇总；
4. 运营令牌查询 SKU 时，返回 SQL 含授权店铺条件；
5. 运营令牌查询无法按店铺隔离的汇总时返回 403；
6. `logs/audit.jsonl` 出现对应身份、状态和耗时记录；
7. 管理员访问 `/metrics` 能看到请求和问数结果计数。

## 8. 域名与 HTTPS

公网长期使用时，应将域名解析到 ECS 公网 IP，并在 Nginx 前配置 HTTPS 证书。未配置域名和证书前，只用于短期受控演示，不通过 HTTP 传输长期有效的生产令牌。

可以选择以下任一生产方案：

- 使用阿里云负载均衡和证书服务终止 HTTPS，再转发到 ECS 80；
- 在 ECS 上增加证书自动续期组件，由 Nginx 监听 443。

当前仓库未包含真实证书，证书和私钥不得提交到 Git。

## 9. 日常运维

```bash
# 状态
docker compose ps

# 最近日志
docker compose logs --tail=100 ai-analytics nginx

# 更新后重新部署
git pull
docker compose up -d --build

# 停止
docker compose down
```

容器使用 `unless-stopped` 自动重启；Docker 标准输出日志最多保留 3 个 10 MiB 文件；问数审计日志持久化在宿主机 `logs/audit.jsonl`。

发布失败时，切回上一个已验证的 Git commit，再执行 `docker compose up -d --build`。不要删除 MaxCompute 表或覆盖业务数据来完成应用回滚。

## 10. 从本地迁移到 ECS 时不变与变化的部分

不变：

- FastAPI、DeepSeek 意图解析、安全 SQL、MaxCompute 执行器；
- API 鉴权、店铺权限、审计和监控；
- Dockerfile、Nginx 配置和健康检查。

变化：

- `NGINX_PORT` 从默认 8080 改为 80；
- 访问地址从 `127.0.0.1:8080` 变成 ECS IP 或域名；
- `.env` 在服务器重新创建，并使用服务器专用密钥；
- 安全组、DNS、HTTPS和云网络由服务器环境负责。
