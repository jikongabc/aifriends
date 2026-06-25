# aifriends 统一开发命令：后端、前端与延迟报告。

PYTHON ?= python
NPM    ?= npm

.PHONY: help install install-frontend migrate run frontend latency check build

help:
	@echo "make install          - 安装后端依赖 (pip install -r backend/requirements.txt)"
	@echo "make install-frontend - 安装前端依赖 (cd frontend && npm install)"
	@echo "make migrate          - 执行数据库迁移 (python manage.py migrate)"
	@echo "make run              - 启动 Django 后端 (python manage.py runserver)"
	@echo "make frontend         - 启动 Vite 前端开发服务器 (npm run dev)"
	@echo "make latency          - 聚合延迟报告 (scripts/latency_report.py)"
	@echo "make check            - Django 系统检查 (python manage.py check)"
	@echo "make build            - 构建前端生产包 (npm run build)"

install:
	$(PYTHON) -m pip install -r backend/requirements.txt

install-frontend:
	cd frontend && $(NPM) install

migrate:
	cd backend && $(PYTHON) manage.py migrate

run:
	cd backend && $(PYTHON) manage.py runserver

frontend:
	cd frontend && $(NPM) run dev

latency:
	cd backend && $(PYTHON) scripts/latency_report.py

check:
	cd backend && $(PYTHON) manage.py check

build:
	cd frontend && $(NPM) run build
