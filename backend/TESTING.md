# 测试说明（离线整批回传与冲突处置）

本目录测试不依赖 Docker/PostgreSQL/Redis，使用 SQLite + FastAPI TestClient 与独立临时库运行；前端组件测试位于仓库外的隔离目录（jsdom + Testing Library），避免污染应用依赖。

## 运行方式

```sh
# 后端：需要 fastapi / sqlalchemy / pydantic / pyjwt / httpx / numpy / redis（仅导入）
cd backend
PYTHONPATH=<依赖目录>:$PWD python3 tests/test_uploads.py       # 服务集成 69 项
PYTHONPATH=<依赖目录>:$PWD python3 tests/test_concurrency.py   # 双线程并发 7 项
PYTHONPATH=<依赖目录>:$PWD python3 tests/test_e2e_flow.py      # 全应用路由 E2E 31 项
# 前端
cd frontend && npm run build    # tsc --noEmit + vite 生产构建
```

## 覆盖口径（与验收点对应）

| 验收点 | 测试位置 |
|---|---|
| 整批内含新样线/已改样线/坏行，保留可接收记录、逐项说明原因 | test_uploads 第1、11组；test_e2e_flow E2E-2 |
| 相同回传重发不增计数、不增修订号，只累计 redeliveries | test_uploads 第2、7组；test_e2e_flow E2E-3 |
| 同批次号不同内容拒绝（409） | test_uploads 第3组 |
| 交错回传重号不整批失败、旧副本不覆盖新计数 | test_uploads 第4组；test_e2e_flow E2E-2 |
| 冲突确认 keep/overwrite，覆盖修订号+1并留处理记录 | test_uploads 第5组；test_e2e_flow E2E-4 |
| 确认期间源数据再变→409、标记重新核对、刷新差异后可再处理 | test_uploads 第6、8组；test_e2e_flow E2E-5 |
| 并发同编号只建档一次、并发相同批次幂等 | test_concurrency C1/C2 |
| 页面查明细、处理冲突、viewer 只读 | test_e2e_flow E2E-4；前端组件测试 5 项 |
| 审计留痕（batch/redelivery/resolved/recheck） | test_uploads 第10组；test_e2e_flow E2E-6 |
| 旧库 content_hash 为空时惰性补算、原单条录入接口不回归 | 手工 legacy 脚本（见提交说明） |

## 已知差异

- SQLite 不支持 `SELECT ... FOR UPDATE`，SQLAlchemy 会忽略行锁；并发安全在 PostgreSQL 上由 `with_for_update()` 与 `upload_batches.batch_ref`、`transects(survey_id,reference)` 唯一约束共同保证，并发测试仅验证应用层对 IntegrityError 的收口逻辑。
- 无浏览器环境，前端以 jsdom 组件测试覆盖交互与请求体，未做真实像素级截图。
