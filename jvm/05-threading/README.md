# 05. Threading — JMM, Memory Barriers, synchronized, Virtual Threads

> "Java thread는 OS thread"는 절반의 답이다. JMM (Java Memory Model)이 정의하는 happens-before 규칙, CPU의 memory barrier, synchronized의 Mark Word 승격(Biased → Lightweight → Heavyweight), Virtual Thread의 Continuation — 이 모든 것이 함께 동작한다.
> 시니어가 알아야 할 것: lock contention 진단, Memory Barrier가 코드 한 줄을 왜 느리게 하는지, Virtual Thread pinning이 carrier thread를 잡는 메커니즘.

---

## 🗺️ JVM 아키텍처 안에서 이 챕터의 위치

```
[Chapter 02-03 Stack/PC/Native] — Per-thread 영역
[Chapter 04 GC] — Safepoint 메커니즘
        │
        ▼
[★ 본 챕터 ★]
   - JMM happens-before 13 규칙
   - Memory Barriers (LoadLoad/StoreStore/LoadStore/StoreLoad)
   - synchronized Mark Word 승격
   - volatile, CAS, AtomicXxx
   - Park/Unpark native (pthread_cond_wait)
   - Virtual Thread Continuation (JDK 21+)
        │
        ▼
[Chapter 10 Ops Scenarios] — VThread pinning 등
```

---

## 📚 Sub-chapter 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-jmm-and-happens-before.md](./01-jmm-and-happens-before.md) | JMM, happens-before 13 규칙, reordering 허용 범위 | ✅ |
| 02 | [02-memory-barriers.md](./02-memory-barriers.md) | LoadLoad/StoreStore/LoadStore/StoreLoad + volatile 구현 | ✅ |
| 03 | [03-synchronized-and-mark-word.md](./03-synchronized-and-mark-word.md) | Biased / Lightweight / Heavyweight Lock + Mark Word 승격 | ✅ |
| 04 | [04-virtual-threads-and-loom.md](./04-virtual-threads-and-loom.md) | Continuation, Pinning, Carrier Thread | ✅ |

---

## 📏 작성 표준 룰

[`../../AGENTS.md`](../../AGENTS.md) 5룰 적용.
