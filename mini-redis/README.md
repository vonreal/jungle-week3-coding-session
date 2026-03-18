# Mini Redis

Mini Redis - 해시 테이블 기반 키-값 저장소

## Architecture

```text
┌─────────────────────────────────────────────┐
│              Mini Redis Server              │
│                                             │
│  ┌──────────────┐    ┌──────────────────┐   │
│  │  Hash Table  │◄──►│ Concurrency Layer│   │
│  │  (core)      │    │ (threading.RLock)│   │
│  └──────┬───────┘    └──────────────────┘   │
│         │                                   │
│  ┌──────▼───────┐    ┌──────────────────┐   │
│  │ TTL Manager  │    │  Persistence     │   │
│  │ lazy+periodic│    │  (optional)      │   │
│  └──────────────┘    └──────────────────┘   │
└─────────────────────────────────────────────┘
                    ▲
                    │
┌─────────────────────────────────────────────┐
│           FastAPI REST API                  │
│  POST /set · GET /get/{key} · DELETE /del   │
│  GET /keys · POST /run-tests · GET /dashboard│
└─────────────────────────────────────────────┘
                    ▲
                    │
┌─────────────────────────────────────────────┐
│         Dashboard UI (single HTML)          │
│  커맨드 패널 │ 키 목록+TTL │ 테스트/벤치마크  │
└─────────────────────────────────────────────┘
                    ▲
                    │
            Browser (localhost:8000)
```

## Installation

TODO

## Run

TODO

## Test

TODO
