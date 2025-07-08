# 课消平台

基于 Flask + SQLite 的课消记录管理系统，支持三权分立权限体系、移动端自适应、操作日志、云端自动部署，适用于教培机构、学校等场景。

## 主要功能
- 学生、课程、课消记录管理
- 用户三类角色：`admin`（超级管理员）、`manager`（管理者）、`user`（普通用户）
- 权限分级：
  - `admin`：可管理所有用户、学生、课消记录，查看操作日志
  - `manager`：可管理普通用户、学生、课消记录
  - `user`：仅能查看自己相关数据
- 课消记录支持操作人追踪、操作日志自动记录
- 支持数据导入导出（Excel）
- 响应式界面，移动端友好
- 云平台（如 Railway）一键部署

## 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/DLshujin/kexiao-platform.git
cd kexiao-platform
```

### 2. 创建虚拟环境并安装依赖
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 初始化数据库
```bash
python init_db.py
```

### 4. 启动项目
```bash
python app.py
```

访问 http://127.0.0.1:5000

### 5. 默认账号
- 管理员：admin / 123456

## 云端部署（Railway等）
- 推送代码到 GitHub 后，云平台会自动拉取并部署
- 如需自定义端口，已适配云平台环境变量

## 权限说明
- `admin` 可添加/编辑/删除所有用户、学生、课消记录，查看操作日志
- `manager` 仅可管理 user、学生、课消记录，不能操作 admin/manager
- `user` 仅能查看自己相关课消数据

## 操作日志
- 所有课消记录的添加、修改、删除均自动记录操作人、时间、类型、变更前后内容
- 仅 admin 可在"操作日志"页面查看所有操作历史

## 移动端适配
- 前端基于 Bootstrap 5，支持手机、平板自适应
- 支持深色模式切换

## 常见问题
- **依赖安装失败**：请确保 Python 3.7+，如遇 numpy/pandas 安装问题可用 wheel 包或指定低版本
- **数据库损坏/乱码**：可用 DB Browser for SQLite 修复或重建
- **权限不生效**：请检查 user 表 role 字段拼写，需为小写（admin/manager/user）
- **云端端口问题**：已自动适配 Railway/Render 等平台

## 贡献与反馈
欢迎提交 issue 或 PR 反馈问题与建议。

---

> 本项目由 DLshujin 开发维护，适用于教培机构课消管理场景。

